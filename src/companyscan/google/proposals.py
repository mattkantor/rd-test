"""Connections, sync and proposals. Reads create pending proposals; only a customer's approval reaches Google."""
import logging
from datetime import timedelta
from urllib.error import HTTPError

from django.utils import timezone

from ..web.models import GoogleLocation
from . import compare, oauth, replies
from .client import ApiError, Client

log = logging.getLogger(__name__)

RENEW_BEFORE = timedelta(seconds=60)


def save_tokens(connection, tokens):
    """Store a token response encrypted; a refresh response has no new refresh token, so keep the old one."""
    connection.token = oauth.encrypt(tokens["access_token"])
    if tokens.get("refresh_token"):
        connection.refresh_token = oauth.encrypt(tokens["refresh_token"])
    connection.expires_at = timezone.now() + timedelta(seconds=int(tokens.get("expires_in") or 3600))
    connection.revoked_at = None
    connection.save()


def revoke(connection):
    """Disconnect: forget the tokens. The picked location and past proposals stay."""
    connection.token = connection.refresh_token = ""
    connection.revoked_at = timezone.now()
    connection.save()


def client_for(connection):
    """An API client with a valid token, refreshed when near expiry. Raises ApiError (and revokes) when Google refuses."""
    if connection.revoked_at or not connection.token:
        raise ApiError("Google is not connected. Reconnect Google.")

    def renew():
        try:
            tokens = oauth.refresh(oauth.decrypt(connection.refresh_token))
        except HTTPError as exc:  # Refused (revoked or expired grant): stop writing and ask for a reconnect.
            log.warning("google connection %s: refresh refused (HTTP %s)", connection.pk, exc.code)
            revoke(connection)
            raise ApiError("Google access was revoked. Reconnect Google.") from exc
        save_tokens(connection, tokens)
        return tokens["access_token"]

    token = renew() if connection.expires_at and connection.expires_at - RENEW_BEFORE < timezone.now() else oauth.decrypt(connection.token)
    return Client(token, renew)


def ensure(location, kind, target, before=None, after=None):
    """The pending proposal for this target, created or updated; None when one was already decided (it is not re-proposed)."""
    found = location.proposals.filter(kind=kind, target=target).first()
    if found and found.status != "pending":
        return None
    if found:
        found.before, found.after = before or {}, after or {}
        found.save(update_fields=["before", "after"])
        return found
    return location.proposals.create(kind=kind, target=target, before=before or {}, after=after or {})


def sync(location, client, draft=replies.draft):
    """Read the listing, claim status, reviews and questions and queue proposals for what needs the customer's decision."""
    name, site = location.location_id, location.connection.site
    data, claimed = client.location(name), client.claimed(name)
    snapshot = {"location": data, "claimed": claimed, "verifications": client.verifications(name)}
    if not claimed:
        snapshot["options"] = client.verification_options(name)
    location.name, location.snapshot, location.read_at = data.get("title") or location.name, snapshot, timezone.now()
    location.save()
    profile = site.profile()
    found = compare.mismatches(data, profile)
    location.proposals.filter(kind="field_edit", status="pending").exclude(target__in=[m["field"] for m in found]).delete()
    for m in found:
        ensure(location, "field_edit", m["field"], {"value": m["current"]}, {"value": m["proposed"]})
    waiting = any(v.get("state") == "PENDING" for v in snapshot["verifications"])
    if not claimed and snapshot["options"] and not waiting:
        ensure(location, "claim_start", "claim", {}, {"method": snapshot["options"][0].get("verificationMethod")})
    for review in client.reviews(location.account, name):
        if not review.get("reviewReply") and not location.proposals.filter(kind="review_reply", target=review["name"]).exists():
            text = draft("review_reply", review.get("comment") or "", review.get("starRating"), profile)
            if text:
                ensure(location, "review_reply", review["name"], {"comment": review.get("comment") or "", "rating": review.get("starRating")}, {"text": text})
    for question in client.questions(name):
        if not question.get("topAnswers") and not location.proposals.filter(kind="qna_answer", target=question["name"]).exists():
            text = draft("qna_answer", question.get("text") or "", None, profile)
            if text:
                ensure(location, "qna_answer", question["name"], {"comment": question.get("text") or ""}, {"text": text})


def nested(path, value):
    body = value
    for key in reversed(path.split(".")):
        body = {key: body}
    return body


def apply(proposal):
    """Write an approved proposal to Google and record the outcome. The only code path that writes."""
    if proposal.status != "approved":
        raise ValueError("Only an approved proposal can be applied")
    location = proposal.location
    try:
        client = client_for(location.connection)
        if proposal.kind == "field_edit":
            client.patch_location(location.location_id, proposal.target, nested(proposal.target, proposal.after["value"]))
        elif proposal.kind == "review_reply":
            client.reply_to_review(proposal.target, proposal.after["text"])
        elif proposal.kind == "qna_answer":
            client.answer_question(proposal.target, proposal.after["text"])
        else:
            proposal.after = {**proposal.after, "result": client.start_verification(location.location_id, proposal.after["method"])}
        proposal.status = "applied"
    except (ApiError, KeyError) as exc:  # Google said no, or the proposal is malformed: keep the old value and say why.
        log.warning("proposal %s (%s) failed", proposal.pk, proposal.kind, exc_info=True)
        proposal.status, proposal.error = "failed", str(exc)[:500]
    proposal.save()


def decide(proposal, user, approve, text=None):
    """The customer's decision on a pending proposal. Reject never touches Google. For a reply, `text` is their edit."""
    if proposal.status != "pending":
        return proposal
    proposal.decided_at, proposal.decided_by = timezone.now(), user
    if not approve:
        proposal.status = "rejected"
        proposal.save()
        return proposal
    if text and text.strip() and proposal.kind in ("review_reply", "qna_answer"):
        proposal.after = {"text": text.strip()}
    proposal.status = "approved"
    proposal.save()
    apply(proposal)
    return proposal


def sync_site(site):
    """Sync the site's picked location; the worker's `google` job and the Sync button run this."""
    connection = site.google_connections.filter(revoked_at__isnull=True).first()
    location = GoogleLocation.objects.filter(connection=connection).first() if connection else None
    if not location:
        raise ValueError("Connect Google and pick a location first.")
    sync(location, client_for(connection))
