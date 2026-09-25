"""Staff-only pages: the site list, the per-run dashboard, bundle files, and the forms that start jobs."""
import json
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.forms import modelform_factory
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..dimensions import DIMENSIONS
from ..scan.crawler import normalize, origin
from . import dashboard, tasks
from .models import Job, Run, Site, sync

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
    if message:
        return back(message)
    run = Run.objects.filter(name=bundle.name).first()
    if return_to == "site" and run:
        return redirect("site", pk=run.site_id)
    return redirect("dashboard", name=bundle.name) if return_to == "dashboard" else back()


@staff_member_required
def index(request):
    sync()
    groups = []
    for site in Site.objects.annotate(n=Count("runs")).filter(n__gt=0):
        groups.append({"pk": site.pk, "site": site.origin, "host": site.host, "runs": site.n, "latest": site.runs.first()})
    groups.sort(key=lambda g: g["latest"].created_at is not None and g["latest"].created_at.timestamp() or 0, reverse=True)
    jobs = {job.site.origin: job for job in Job.objects.select_related("site").order_by("started")}  # Latest per site wins.
    pending = Job.objects.filter(state="running", site__runs__isnull=True).select_related("site")
    return render(request, "index.html", {"message": request.GET.get("msg", ""), "sites": groups, "jobs": jobs,
                                          "dimensions": DIMENSIONS, "pending": pending})


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


def render_run(request, name, on_site=False):
    """The dashboard for one crawl bundle, with its site's run history. on_site: rendered as the site page."""
    bundle = bundle_path(name)
    manifest = dashboard.read(bundle, "manifest.json") if bundle else None
    if not (isinstance(manifest, dict) and "counts" in manifest):  # Crawl bundles only.
        raise Http404
    sort, desc = request.GET.get("sort", "id"), request.GET.get("desc", "") in {"1", "true"}
    url = crawl_url(bundle)  # None for a tampered input_url: the dashboard still renders, without job status.
    job = Job.objects.filter(site__origin=origin(url)).first() if url else None
    run = Run.objects.filter(name=name).select_related("site").first()
    # Render from root/name, not the resolved path: file_url is relative to the unresolved root (macOS /var symlink).
    view = settings.COMPANYSCAN_OUTPUT / name
    return render(request, "dashboard.html", {"m": dashboard.load(view, sort, desc), "bundle": view, "job": job,
                                              "percent": job.percent if job else 0, "site": run.site if run else None,
                                              "history": run.site.runs.all() if run else [], "on_site": on_site})


@staff_member_required
def job_status(request, name):
    """Just the job panel, for the dashboard to poll while a job runs."""
    bundle = bundle_path(name)
    url = crawl_url(bundle)
    if not url:
        raise Http404
    job = Job.objects.filter(site__origin=origin(url)).first()
    return render(request, "job.html", {"job": job, "percent": job.percent if job else 0, "bundle": settings.COMPANYSCAN_OUTPUT / name,
                                        "site": Site.objects.filter(origin=origin(url)).first()})


@staff_member_required
def site_job(request, pk):
    """The home page's small status for a site's latest job, polled while it runs."""
    return render(request, "job_mini.html", {"job": get_object_or_404(Site, pk=pk).jobs.first()})


@staff_member_required
def site_page(request, pk):
    """A site's current assessment (its latest crawl) plus the history of older ones."""
    sync()
    run = get_object_or_404(Site, pk=pk).runs.first()
    if not run:
        raise Http404
    return render_run(request, run.name, on_site=True)


# The origin is the site's identity (runs attach to it by URL), so it is set once, by the first crawl, never edited.
SiteForm = modelform_factory(Site, fields=["business_name", "icp", "city", "state", "country"])


@staff_member_required
def site_edit(request, pk):
    site = get_object_or_404(Site, pk=pk)
    form = SiteForm(request.POST or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("site", pk=site.pk) if site.runs.exists() else back()
    return render(request, "site_edit.html", {"site": site, "form": form})


@staff_member_required
def run_dashboard(request, name):
    sync()
    return render_run(request, name)


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
