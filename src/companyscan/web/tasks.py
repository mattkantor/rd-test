"""Crawl, report and re-crawl jobs, run by the Huey worker (`python manage.py run_huey`)."""
import logging
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone as dj_timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from .. import blog
from ..cli import directory_name, parser, run
from ..report.analyze import analyze
from ..report.pdf import render_pdf
from ..scan.crawler import origin
from .models import BlogPost, Job, Site, remember, sync

log = logging.getLogger(__name__)


def new_run(url):
    return f"{directory_name(url)}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"


def start(url, kind, label, run, dimensions=()):
    """Create a running Job and queue it; None if the site already has one running."""
    site = Site.objects.get_or_create(origin=origin(url))[0]
    try:
        with transaction.atomic():
            job = Job.objects.create(site=site, kind=kind, url=url, dimensions=list(dimensions), run=run, label=label)
    except IntegrityError:  # one_running_job_per_site.
        log.info("%s for %s not queued: a job is already running", kind, url)
        return None
    log.info("queued %s job %s for %s (run %s)", kind, job.pk, url, run)
    execute(job.pk)
    return job


def crawl(job, progress):
    args = parser().parse_args(["scan", job.url, *job.site.scan_args()] + [arg for d in job.dimensions for arg in ("--dimension", d)])
    # Stored questions for this profile; a dimension with none yet takes the newest matching bundle's, then they're stored.
    args.saved_questions = job.site.saved_questions()
    args.site_reads = {job.site.site_read["key"]: job.site.site_read} if job.site.site_read else {}
    result = run(args, output=settings.COMPANYSCAN_OUTPUT / job.run, progress=progress)
    remember(job.site, settings.COMPANYSCAN_OUTPUT / job.run)
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
        log.exception("re-crawl of %s: crawl kept, report failed", job.run)
        raise ValueError(f"{crawled}, but the report failed: {exc}") from exc
    return f"{crawled} · report ready"


def draft_posts(job, progress):
    """Draft the site's scheduled number of posts from its profile and the crawl in job.run; every one waits as a draft."""
    site, bundle = job.site, settings.COMPANYSCAN_OUTPUT / job.run
    made = 0
    for n in range(1, max(site.blog_per_run, 1) + 1):
        recent = list(site.posts.values_list("keyword", flat=True)[:blog.REPEAT_WINDOW])
        keyword = blog.next_keyword(site.keywords, recent, site.blog_repeat_keywords)
        if not keyword:
            break
        progress(n, site.blog_per_run, f"Drafting a post on “{keyword}”")
        BlogPost.objects.create(site=site, keyword=keyword, run=job.run, profile=site.profile(), **blog.generate(site.profile(), keyword, bundle))
        made += 1
    if not made:
        raise ValueError("No post drafted: add keywords, or every keyword was used in the last posts.")
    return f"Drafted {made} post(s) for approval"


def due_sites(now):
    """Sites with a schedule and a keyword to use, a crawl, and a last draft older than their frequency (or none yet)."""
    for site in Site.objects.filter(blog_every_days__isnull=False, blog_every_days__gt=0).exclude(keywords=""):
        last = site.posts.first()
        recent = list(site.posts.values_list("keyword", flat=True)[:blog.REPEAT_WINDOW])
        if not blog.next_keyword(site.keywords, recent, site.blog_repeat_keywords):
            continue  # Nothing to write about: don't queue a job that can only fail.
        if site.runs.exists() and (not last or last.created_at + timedelta(days=site.blog_every_days) <= now):
            yield site


@db_periodic_task(crontab(minute="0"))
def schedule_blogs():
    """Hourly: queue a drafting job for each site that is due (one running job per site still applies)."""
    for site in due_sites(dj_timezone.now()):
        start(site.origin, "blog", "Drafting blog posts…", site.runs.first().name)


WORK = {"crawl": crawl, "recrawl": recrawl, "report": report, "blog": draft_posts}


@db_task()
def execute(job_id):
    job = Job.objects.get(pk=job_id)

    def progress(step, steps, label, done=None, total=None, unit=""):
        count = f": {done} of {total} {unit}".rstrip() if total else ""
        Job.objects.filter(pk=job_id).update(step=step, steps=steps, label=label + count, done=done, total=total, unit=unit)

    log.info("%s job %s started for %s (run %s)", job.kind, job_id, job.url or job.site, job.run)
    began = time.monotonic()
    try:
        state, label = "done", WORK[job.kind](job, progress)
    except Exception as exc:  # Job boundary: surface every failure in the UI instead of losing it.
        log.exception("%s job %s for %s failed", job.kind, job_id, job.url or job.site)
        state, label = "error", str(exc)
    log.info("%s job %s %s in %.1fs: %s", job.kind, job_id, state, time.monotonic() - began, label)
    Job.objects.filter(pk=job_id).update(state=state, label=label, finished=dj_timezone.now())
    sync()
