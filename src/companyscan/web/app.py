"""FastAPI UI: enter a URL, crawl it, see when each site was last crawled, generate the LLM report + PDF."""
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import ChainableUndefined

from ..dimensions import DIMENSIONS
from ..report.analyze import latest
from ..scan.crawler import normalize, origin
from . import dashboard, jobs

# Same default as the CLI (./output from where you run it); set COMPANYSCAN_OUTPUT when deployed.
ROOT = Path(os.environ.get("COMPANYSCAN_OUTPUT", "output")).resolve()
VIEWS = Path(__file__).resolve().parents[1] / "views"
LOCAL = ["127.0.0.1", "localhost"]


def sites(root):
    """Latest crawl per site from the manifests on disk; manifest created_at is the last-crawled date."""
    runs = []
    for manifest in root.glob("*/manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            site = origin(normalize(data["input_url"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if "counts" not in data:  # Not a crawl bundle (e.g. a standalone reputation check).
            continue
        counts = data["counts"] if isinstance(data["counts"], dict) else {}
        config = data.get("config") if isinstance(data.get("config"), dict) else {}
        runs.append({"dir": manifest.parent, "site": site, "created_at": data["created_at"] if isinstance(data.get("created_at"), str) else "",
                     "status": data.get("status"), "pages": counts.get("pages", 0),
                     "dimensions": config["dimensions"] if isinstance(config.get("dimensions"), list) else [],
                     "report": latest(manifest.parent, "report.md"), "pdf": latest(manifest.parent, "report.pdf")})
    grouped = {}
    for r in sorted(runs, key=lambda r: r["created_at"]):
        group = grouped.setdefault(r["site"], {"site": r["site"], "host": urlsplit(r["site"]).netloc, "runs": 0})
        group["runs"] += 1
        group["latest"] = r
    return sorted(grouped.values(), key=lambda g: g["latest"]["created_at"], reverse=True)


def local_time(when):
    try:
        return datetime.fromisoformat(when).astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):  # Tampered manifests can hold null or numbers here.
        return "?"


def bundle_path(root, name):
    """Resolved bundle directory inside root that has a manifest.json, or None (blocks ../ escapes)."""
    bundle = (Path(root) / name).resolve()
    return bundle if bundle.is_relative_to(Path(root).resolve()) and (bundle / "manifest.json").is_file() else None


def create_app(root=ROOT):
    root = Path(root)
    app = FastAPI(title="Company Footprint", docs_url=None, redoc_url=None, openapi_url=None)
    # Localhost-only UI: other Host headers (DNS rebinding) and cross-site form posts (CSRF) are refused.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL)

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        source = request.headers.get("origin")
        if request.method == "POST" and source and urlsplit(source).hostname not in LOCAL:
            return PlainTextResponse("Forbidden", status_code=403)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=VIEWS / "static"), name="static")
    templates = Jinja2Templates(directory=VIEWS / "templates")
    templates.env.undefined = ChainableUndefined  # A missing nested key in bundle data renders empty instead of raising.
    templates.env.filters["local_time"] = local_time
    templates.env.filters["file_url"] = lambda path: "/files/" + quote(path.relative_to(root).as_posix())
    templates.env.filters["href"] = dashboard.link
    templates.env.filters["badge"] = dashboard.badge

    def dashboard_or_home(bundle, return_to):
        # Built from the validated bundle's own name, so the form can't redirect anywhere else.
        return RedirectResponse(f"/run/{quote(bundle.name)}", status_code=303) if return_to == "dashboard" else back()

    def back(message=""):
        return RedirectResponse("/" + (f"?{urlencode({'msg': message})}" if message else ""), status_code=303)

    @app.get("/")
    def index(request: Request, msg: str = ""):
        return templates.TemplateResponse(request, "index.html", {
            "message": msg, "sites": sites(root), "jobs": jobs.JOBS, "dimensions": DIMENSIONS,
            "running": any(j["state"] == "running" for j in jobs.JOBS.values())})

    @app.post("/crawl")
    def crawl(background: BackgroundTasks, url: str = Form(), dimension: list[str] = Form(default=[])):
        try:
            url = normalize(url.strip())
        except ValueError as exc:
            return back(str(exc))
        work = jobs.crawl(url, [d for d in dimension if d in DIMENSIONS], root)
        if not jobs.claim(origin(url), "Crawling…", "crawl", work.run):
            return back("That site already has a job running.")
        background.add_task(jobs.execute, origin(url), work)
        return back()

    @app.post("/report")
    def report(background: BackgroundTasks, dir: str = Form(), return_to: str = Form("")):
        bundle = bundle_path(root, dir)
        if not bundle:
            return back("Unknown crawl.")
        site = origin(normalize(json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["input_url"]))
        if not jobs.claim(site, "Starting report…", "report", bundle.name):
            return back("That site already has a job running.")
        background.add_task(jobs.execute, site, jobs.report(bundle))
        return dashboard_or_home(bundle, return_to)

    @app.post("/recrawl")
    def recrawl(background: BackgroundTasks, dir: str = Form(), return_to: str = Form("")):
        """Crawl the bundle's site again with every check, then write its report. A new timestamped run; the old one is kept."""
        bundle = bundle_path(root, dir)
        manifest = dashboard.read(bundle, "manifest.json") if bundle else None
        try:
            url = normalize(manifest["input_url"]) if isinstance(manifest, dict) and "counts" in manifest else None
        except (KeyError, TypeError, ValueError):
            url = None
        if not url:
            return back("Unknown crawl.")
        work = jobs.recrawl(url, root)
        if not jobs.claim(origin(url), "Re-crawling with every check, then the report…", "recrawl", work.run):
            return back("That site already has a job running.")
        background.add_task(jobs.execute, origin(url), work)
        return dashboard_or_home(bundle, return_to)

    @app.get("/run/{name}")
    def run_dashboard(request: Request, name: str, sort: str = "id", desc: bool = False):
        bundle = bundle_path(root, name)
        manifest = dashboard.read(bundle, "manifest.json") if bundle else None
        if not (isinstance(manifest, dict) and "counts" in manifest):  # Crawl bundles only.
            raise HTTPException(404)
        # Render from root/name, not the resolved path: file_url is relative to the unresolved root (macOS /var symlink).
        view = root / name
        try:
            job = jobs.JOBS.get(origin(normalize(manifest["input_url"])))
        except (KeyError, TypeError, ValueError):
            job = None
        return templates.TemplateResponse(request, "dashboard.html", {"m": dashboard.load(view, sort, desc), "bundle": view,
                                                                      "job": job, "percent": jobs.percent(job) if job else 0})

    @app.get("/files/{path:path}")
    def files(path: str):
        target = (root / path).resolve()
        if not (target.is_relative_to(root.resolve()) and target.is_file()):
            raise HTTPException(404)
        # Show Markdown and JSON in the browser rather than downloading them.
        return FileResponse(target, media_type="text/plain; charset=utf-8" if target.suffix in {".md", ".json"} else None)

    return app


def serve(port=8765):
    import uvicorn

    ROOT.mkdir(exist_ok=True)
    print(f"Company Footprint UI: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
