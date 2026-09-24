"""Staff-only pages: the site list, the per-run dashboard, bundle files, and the forms that start jobs."""
import json
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ..dimensions import DIMENSIONS
from ..scan.crawler import normalize, origin
from . import dashboard, tasks
from .models import Job, Site, sync

BUSY = "That site already has a job running."


def bundle_path(name):
    """Resolved bundle directory inside the output root that has a manifest.json, or None (blocks ../ escapes)."""
    root = settings.COMPANYSCAN_OUTPUT.resolve()
    bundle = (root / name).resolve()
    return bundle if bundle.is_relative_to(root) and (bundle / "manifest.json").is_file() else None


def crawl_url(bundle):
    """The input URL of a crawl bundle (manifest with counts), or None."""
    manifest = dashboard.read(bundle, "manifest.json") if bundle else None
    try:
        return normalize(manifest["input_url"]) if isinstance(manifest, dict) and "counts" in manifest else None
    except (KeyError, TypeError, ValueError):
        return None


def back(message=""):
    return redirect("/" + (f"?{urlencode({'msg': message})}" if message else ""))


def dashboard_or_home(bundle, return_to, message=""):
    # Built from the validated bundle's own name, so the form can't redirect anywhere else.
    return redirect("dashboard", name=bundle.name) if return_to == "dashboard" and not message else back(message)


@staff_member_required
def index(request):
    sync()
    groups = []
    for site in Site.objects.annotate(n=Count("runs")).filter(n__gt=0):
        groups.append({"site": site.origin, "host": site.host, "runs": site.n, "latest": site.runs.first()})
    groups.sort(key=lambda g: g["latest"].created_at is not None and g["latest"].created_at.timestamp() or 0, reverse=True)
    jobs = {job.site.origin: job for job in Job.objects.select_related("site").order_by("started")}  # Latest per site wins.
    return render(request, "index.html", {"message": request.GET.get("msg", ""), "sites": groups, "jobs": jobs,
                                          "dimensions": DIMENSIONS, "running": Job.objects.filter(state="running").exists()})


@staff_member_required
@require_POST
def crawl(request):
    try:
        url = normalize(request.POST.get("url", "").strip())
    except ValueError as exc:
        return back(str(exc))
    dimensions = [d for d in request.POST.getlist("dimension") if d in DIMENSIONS]
    return back() if tasks.start(url, "crawl", "Crawling…", tasks.new_run(url), dimensions) else back(BUSY)


@staff_member_required
@require_POST
def report(request):
    bundle = bundle_path(request.POST.get("dir", ""))
    url = crawl_url(bundle)
    if not url:
        return back("Unknown crawl.")
    job = tasks.start(url, "report", "Starting report…", bundle.name)
    return dashboard_or_home(bundle, request.POST.get("return_to"), "" if job else BUSY)


@staff_member_required
@require_POST
def recrawl(request):
    """Crawl the bundle's site again with every check, then write its report. A new timestamped run; the old one is kept."""
    bundle = bundle_path(request.POST.get("dir", ""))
    url = crawl_url(bundle)
    if not url:
        return back("Unknown crawl.")
    job = tasks.start(url, "recrawl", "Re-crawling with every check, then the report…", tasks.new_run(url), DIMENSIONS)
    return dashboard_or_home(bundle, request.POST.get("return_to"), "" if job else BUSY)


@staff_member_required
def run_dashboard(request, name):
    bundle = bundle_path(name)
    manifest = dashboard.read(bundle, "manifest.json") if bundle else None
    if not (isinstance(manifest, dict) and "counts" in manifest):  # Crawl bundles only.
        raise Http404
    sort, desc = request.GET.get("sort", "id"), request.GET.get("desc", "") in {"1", "true"}
    url = crawl_url(bundle)  # None for a tampered input_url: the dashboard still renders, without job status.
    job = Job.objects.filter(site__origin=origin(url)).first() if url else None
    # Render from root/name, not the resolved path: file_url is relative to the unresolved root (macOS /var symlink).
    view = settings.COMPANYSCAN_OUTPUT / name
    return render(request, "dashboard.html", {"m": dashboard.load(view, sort, desc), "bundle": view, "job": job,
                                              "percent": job.percent if job else 0})


@staff_member_required
def files(request, path):
    root = settings.COMPANYSCAN_OUTPUT.resolve()
    target = (root / path).resolve()
    if not (target.is_relative_to(root) and target.is_file()):
        raise Http404
    # Show Markdown and JSON in the browser rather than downloading them.
    response = FileResponse(target.open("rb"))
    if target.suffix in {".md", ".json"}:
        response["Content-Type"] = "text/plain; charset=utf-8"
    return response
