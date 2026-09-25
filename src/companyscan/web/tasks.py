"""Crawl, report and re-crawl jobs, run by the Huey worker (`python manage.py run_huey`)."""
from datetime import datetime, timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone
from huey.contrib.djhuey import db_task

from ..cli import directory_name, parser, run
from ..report.analyze import analyze
from ..report.pdf import render_pdf
from ..scan.crawler import origin
from .models import Job, Site, sync


def new_run(url):
    return f"{directory_name(url)}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"


def start(url, kind, label, run, dimensions=()):
    """Create a running Job and queue it; None if the site already has one running."""
    site = Site.objects.get_or_create(origin=origin(url))[0]
    try:
        with transaction.atomic():
            job = Job.objects.create(site=site, kind=kind, url=url, dimensions=list(dimensions), run=run, label=label)
    except IntegrityError:  # one_running_job_per_site.
        return None
    execute(job.pk)
    return job


def crawl(job, progress):
    args = parser().parse_args(["scan", job.url, *job.site.scan_args()] + [arg for d in job.dimensions for arg in ("--dimension", d)])
    result = run(args, output=settings.COMPANYSCAN_OUTPUT / job.run, progress=progress)
    return f"Crawled {result['counts']['pages']} pages ({result['status']})"


def report(job, progress, step=1, steps=2):
    bundle = settings.COMPANYSCAN_OUTPUT / job.run
    progress(step, steps, "Writing the report (this takes a few minutes)")
    analyze(bundle)
    progress(step + 1, steps, "Rendering PDF")
    render_pdf(bundle)
    return "Report ready"


def recrawl(job, progress):
    """Everything in one job: crawl with every dimension (the caller sets them), then the report on the new run."""
    crawl_steps = [0]

    def crawl_progress(step, steps, label, done=None, total=None, unit=""):
        crawl_steps[0] = steps
        progress(step, steps + 2, label, done, total, unit)  # +2: the report's analysis and PDF steps.

    crawled = crawl(job, crawl_progress)
    try:
        report(job, progress, crawl_steps[0] + 1, crawl_steps[0] + 2)
    except Exception as exc:  # The new run is on disk either way; say which half failed.
        raise ValueError(f"{crawled}, but the report failed: {exc}") from exc
    return f"{crawled} · report ready"


WORK = {"crawl": crawl, "recrawl": recrawl, "report": report}


@db_task()
def execute(job_id):
    job = Job.objects.get(pk=job_id)

    def progress(step, steps, label, done=None, total=None, unit=""):
        count = f": {done} of {total} {unit}".rstrip() if total else ""
        Job.objects.filter(pk=job_id).update(step=step, steps=steps, label=label + count, done=done, total=total, unit=unit)

    try:
        state, label = "done", WORK[job.kind](job, progress)
    except Exception as exc:  # Job boundary: surface every failure in the UI instead of losing it.
        state, label = "error", str(exc)
    Job.objects.filter(pk=job_id).update(state=state, label=label, finished=dj_timezone.now())
    sync()
