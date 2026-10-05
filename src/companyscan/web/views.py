"""Staff-only pages: the site list, the per-run dashboard, bundle files, and the forms that start jobs."""
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.forms import modelform_factory
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..dimensions import DIMENSIONS
from ..report import scorecard as card
from ..report.analyze import hidden, latest, load as load_json
from ..report.fixpack import zipped
from ..report.scorecard import render_scorecard
from ..scan.crawler import normalize, origin
from . import dashboard, tasks
from .models import QUESTIONS, Job, QuestionSet, Run, Site, sync

log = logging.getLogger(__name__)

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
    # Stored snapshots, so "Since last run" and the trend lines still find runs whose bundles were deleted.
    before = list(run.site.snapshots.filter(created_at__lt=run.created_at)) if run and run.created_at else None
    earlier = [(s.name, s.created_at.isoformat(), s.checks.get) for s in before] if before is not None else None
    history = [(s.created_at.isoformat(), s.metrics) for s in reversed(before or [])]  # Oldest first.
    return render(request, "dashboard.html", {"m": dashboard.load(view, sort, desc, earlier, history), "bundle": view, "job": job,
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


def public_site(request, public_id):
    """The customer's own page: a cut-down scorecard for the site's latest reported crawl, at an unguessable URL so it
    needs no login. Scores and copy come from scorecard.build; the template escapes everything (report text is untrusted)."""
    site = get_object_or_404(Site, public_id=public_id)
    run = next((r for r in site.runs.all() if bundle_path(r.name) and latest(bundle_path(r.name), "analysis.json")), None)
    if not run:
        raise Http404
    bundle = bundle_path(run.name)
    analysis = load_json(latest(bundle, "analysis.json"))
    if not isinstance(analysis, dict):
        raise Http404
    data = card.build(analysis, site.customer_ltv, site.target_customers, hidden(bundle), load_json(bundle / "technical/measurement.json"))
    scored = [a for a in data["areas"] if a["score"] is not None]
    improve = sorted((a for a in scored if a["score"] < 80), key=lambda a: a["score"])
    return render(request, "public_site.html", {
        "site": site, "name": site.business_name or site.host, "run": run, "c": data, "stages": card.stages(data["areas"]),
        "improve": improve, "working": [a for a in scored if a["score"] >= 80], "why": card.WHY, "why_default": card.WHY_DEFAULT,
        "band": card.band, "money": card.money, "question": card.QUESTION, "service": card.service()})


# The origin is the site's identity (runs attach to it by URL), so it is set once, by the first crawl, never edited.
SiteForm = modelform_factory(Site, fields=["business_name", "icp", "category", "people", "aliases", "profiles",
                                           "city", "state", "country", "customer_ltv", "target_customers", "place_id"])


def suggestions(site):
    """Blank fingerprint fields pre-filled from the latest crawl's identity profile, for the user to confirm and save."""
    run = site.runs.first()
    data = {}
    for name in ("ai_search", "llm_reputation"):
        data = dashboard.as_dict(dashboard.read(run.dir, f"technical/{name}.json")) if run else {}
        if dashboard.as_dict(data.get("profile")):
            break
    profile = dashboard.as_dict(data.get("profile"))
    found = dashboard.as_dict(dashboard.as_dict(data.get("site_read")).get("identity"))
    names = [n for n in dashboard.as_list(profile.get("names")) if isinstance(n, str)]
    main = (site.business_name or (names[0] if names else "")).lower()
    text = lambda values: "\n".join(v for v in values if isinstance(v, str))
    values = {"category": found.get("category") if isinstance(found.get("category"), str) else
                          text(dashboard.as_list(profile.get("categories"))[:1]),
              "people": text(dashboard.as_list(profile.get("people"))),
              "aliases": text(n for n in names if n.lower() != main),
              "profiles": text(dashboard.as_list(profile.get("profiles")))}
    return {key: value for key, value in values.items() if value and not getattr(site, key)}


@staff_member_required
def site_edit(request, pk):
    site = get_object_or_404(Site, pk=pk)
    suggested = {} if request.method == "POST" else suggestions(site)
    form = SiteForm(request.POST or None, instance=site, initial=suggested)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("site", pk=site.pk) if site.runs.exists() else back()
    return render(request, "site_edit.html", {"site": site, "form": form, "suggested": [form[key].label for key in suggested],
                                              "question_sets": site.question_sets.filter(**site.question_key())})


@staff_member_required
@require_POST
def new_questions(request, pk):
    """Empty this profile's stored question sets so the next crawl writes, and stores, new ones."""
    site = get_object_or_404(Site, pk=pk)
    for kind in QUESTIONS:
        QuestionSet.objects.update_or_create(site=site, kind=kind, **site.question_key(), defaults={"items": [], "run": ""})
    return redirect("site_edit", pk=site.pk)


@staff_member_required
def run_dashboard(request, name):
    sync()
    return render_run(request, name)


@staff_member_required
def scorecard(request, name):
    """Render the run's customer scorecard PDF from its newest analysis and the site's current LTV and goal."""
    bundle = bundle_path(name)
    run = Run.objects.filter(name=name).select_related("site").first()
    if not bundle or not run:
        raise Http404
    try:
        pdf = render_scorecard(bundle, run.site.customer_ltv, run.site.target_customers)
    except ValueError as exc:  # No report yet, or no Chrome.
        log.warning("scorecard for %s: %s", name, exc, exc_info=True)
        return back(str(exc))
    return FileResponse(pdf.open("rb"), content_type="application/pdf", filename=f"{run.site.host}-scorecard.pdf")


@staff_member_required
def fixpack(request, name):
    """The run's fix pack as a zip, built from its newest analysis so it always matches the report."""
    bundle = bundle_path(name)
    if not bundle or not Run.objects.filter(name=name).exists():
        raise Http404
    try:
        filename, data = zipped(bundle)
    except ValueError as exc:  # No report yet.
        log.warning("fix pack for %s: %s", name, exc)
        return back(str(exc))
    return HttpResponse(data, content_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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
