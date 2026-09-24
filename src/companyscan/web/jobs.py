"""Background crawl and report jobs, one at a time per site."""
import threading
from datetime import datetime, timezone

from ..cli import directory_name, parser, run
from ..dimensions import DIMENSIONS
from ..report.analyze import analyze
from ..report.pdf import render_pdf

# ponytail: in-memory job table, lost on restart; the bundle and report on disk are the durable record.
JOBS, LOCK = {}, threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def claim(key, label, kind=None, run=None):
    """Mark a site busy; False if it already has a job running. `run` is the bundle folder the job writes or reads."""
    with LOCK:
        if JOBS.get(key, {}).get("state") == "running":
            return False
        JOBS[key] = {"state": "running", "label": label, "kind": kind, "run": run, "step": 0, "steps": 0,
                     "done": None, "total": None, "unit": "", "started": now(), "finished": None}
        return True


def execute(key, work):
    job = JOBS.setdefault(key, {"state": "running", "label": ""})

    def progress(step, steps, label, done=None, total=None, unit=""):
        count = f": {done} of {total} {unit}".rstrip() if total else ""
        job.update(step=step, steps=steps, label=label + count, done=done, total=total, unit=unit)

    try:
        job.update(state="done", label=work(progress))
    except Exception as exc:  # Job boundary: surface every failure in the UI instead of losing it.
        job.update(state="error", label=str(exc))
    job["finished"] = now()


def percent(job):
    """Overall 0-100: finished steps plus the fraction done in the current one."""
    if job.get("state") == "done":
        return 100
    step, steps = job.get("step") or 0, job.get("steps") or 0
    if not steps:
        return 0
    fraction = min(job["done"] / job["total"], 1) if job.get("total") and job.get("done") is not None else 0
    return max(0, min(100, int((step - 1 + fraction) / steps * 100)))


def crawl(url, dimensions, root):
    args = parser().parse_args(["scan", url] + [arg for d in dimensions for arg in ("--dimension", d)])
    output = root / f"{directory_name(url)}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"

    def work(progress):
        result = run(args, output=output, progress=progress)
        return f"Crawled {result['counts']['pages']} pages ({result['status']})"
    work.run = output.name  # ponytail: the new bundle's folder, so the dashboard can link to it when done.
    return work


def recrawl(url, root):
    """Everything in one job: crawl with every dimension (WCAG and the technical checks always run), then the report."""
    crawl_work = crawl(url, list(DIMENSIONS), root)

    def work(progress):
        crawl_steps = [0]

        def crawl_progress(step, steps, label, done=None, total=None, unit=""):
            crawl_steps[0] = steps
            progress(step, steps + 2, label, done, total, unit)  # +2: the report's analysis and PDF steps.

        crawled = crawl_work(crawl_progress)
        n = crawl_steps[0]
        bundle = root / crawl_work.run
        try:
            progress(n + 1, n + 2, "Writing the report (this takes a few minutes)")
            analyze(bundle)
            progress(n + 2, n + 2, "Rendering PDF")
            render_pdf(bundle)
        except Exception as exc:  # The new run is on disk either way; say which half failed.
            raise ValueError(f"{crawled}, but the report failed: {exc}") from exc
        return f"{crawled} · report ready"
    work.run = crawl_work.run
    return work


def report(bundle):
    def work(progress):
        progress(1, 2, "Writing the report (this takes a few minutes)")
        analyze(bundle)
        progress(2, 2, "Rendering PDF")
        render_pdf(bundle)
        return "Report ready"
    return work
