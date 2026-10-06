"""Local business page: connect Google, pick the listing, and approve what the agent proposes. Every view is scoped to the
signed-in customer's own sites (404 otherwise); nothing here writes to Google except an approved proposal."""
import logging
import secrets
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from ..google import compare, oauth, proposals
from ..google.client import ApiError
from . import tasks
from .models import GoogleConnection, GoogleLocation, Proposal
from .portal import page

log = logging.getLogger(__name__)

MENU = {"claim_start": 0, "field_edit": 1, "review_reply": 2, "qna_answer": 3}


def back(message=""):
    return redirect("/portal/local" + (f"?{urlencode({'msg': message})}" if message else ""))


def active(site):
    return site.google_connections.filter(revoked_at__isnull=True).first()


@login_required
def local(request):
    cards = []
    for site in request.user.sites.all():
        connection = site.google_connections.order_by("-id").first()
        live = connection if connection and not connection.revoked_at else None
        location = GoogleLocation.objects.filter(connection=connection).first() if connection else None
        choices, error = [], ""
        if live and not location:  # Connected, no listing picked yet: list what this account manages.
            try:
                choices = [{**loc, "match": compare.matches_site(loc, site.profile())} for loc in proposals.client_for(live).locations()]
            except ApiError as exc:
                error = str(exc)
        queue = sorted(location.proposals.filter(status="pending"), key=lambda p: MENU[p.kind]) if location else []
        cards.append({"site": site, "connected": bool(live), "reconnect": bool(connection and connection.revoked_at and location),
                      "location": location, "choices": choices, "error": error, "queue": queue,
                      "done": location.proposals.exclude(status="pending")[:20] if location else [],
                      "snap": location.snapshot if location else {}, "job": site.jobs.filter(kind="google").first()})
    return page(request, "Local business", "portal/local.html", cards=cards, message=request.GET.get("msg", ""))


@login_required
def connect(request, site_pk):
    site = get_object_or_404(request.user.sites, pk=site_pk)
    state = secrets.token_urlsafe(24)
    request.session["google_oauth"] = {"state": state, "site": site.pk}
    try:
        return redirect(oauth.consent_url(state))
    except ValueError as exc:  # Not configured.
        return back(str(exc))


@login_required
def callback(request):
    """Google sends the customer back here. The state must match the one stored in their session (login CSRF)."""
    saved = request.session.pop("google_oauth", None)
    if not saved or not secrets.compare_digest(saved["state"], request.GET.get("state", "")):
        return back("That Google sign-in could not be verified. Please try again.")
    site = get_object_or_404(request.user.sites, pk=saved["site"])
    if request.GET.get("error") or not request.GET.get("code"):
        return back("Google did not connect.")
    try:
        tokens = oauth.exchange(request.GET["code"])
    except (OSError, ValueError) as exc:
        log.warning("google connect for site %s failed: %s", site.pk, type(exc).__name__)
        return back("Google did not accept the sign-in.")
    # Reconnecting reuses the row, so the picked listing and its proposals stay.
    connection = site.google_connections.order_by("-id").first() or GoogleConnection(site=site, user=request.user)
    connection.user = request.user
    proposals.save_tokens(connection, tokens)
    return back("Google connected.")


@login_required
@require_POST
def pick(request, site_pk):
    site = get_object_or_404(request.user.sites, pk=site_pk)
    connection = active(site)
    if not connection:
        return back("Connect Google first.")
    try:  # Re-read what the account manages: the posted name is only a choice among those.
        chosen = next((loc for loc in proposals.client_for(connection).locations() if loc["name"] == request.POST.get("location")), None)
    except ApiError as exc:
        return back(str(exc))
    if not chosen:
        return back("That location is not managed by this Google account.")
    if not compare.matches_site(chosen, site.profile()) and not request.POST.get("confirm"):
        return back("Neither the website nor the phone matches this site. Tick the box to confirm it is your business.")
    GoogleLocation.objects.update_or_create(connection=connection, defaults={
        "account": chosen["account"], "location_id": chosen["name"], "name": chosen.get("title", ""), "snapshot": {}, "read_at": None})
    tasks.start(site.origin, "google", "Reading the Google listing…", "")
    return back("Listing chosen.")


@login_required
@require_POST
def sync(request, site_pk):
    site = get_object_or_404(request.user.sites, pk=site_pk)
    return back() if tasks.start(site.origin, "google", "Reading the Google listing…", "") else back("A job is already running for this site.")


@login_required
@require_POST
def disconnect(request, site_pk):
    connection = active(get_object_or_404(request.user.sites, pk=site_pk))
    if connection:
        proposals.revoke(connection)
    return back("Google disconnected.")


@login_required
@require_POST
def decide(request, pk, action):
    proposal = get_object_or_404(Proposal, pk=pk, location__connection__site__user=request.user)
    if action in ("approve", "reject"):
        proposals.decide(proposal, request.user, action == "approve", request.POST.get("text"))
    return back()
