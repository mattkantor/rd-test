"""Google Business Profile: OAuth and token storage, comparison, proposals that wait for approval, and writes only on approval.
Google is always stubbed; no test touches the network."""
import io
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from test_report import StubReport
from test_web import DJANGO, WebCase, bundle

from companyscan.google import client as api, compare

if DJANGO:
    from cryptography.fernet import Fernet
    from django.contrib.auth.models import User
    from companyscan.google import oauth, proposals, replies
    from companyscan.web.models import GoogleConnection, GoogleLocation, Proposal, Site, sync

PROFILE = {"business_name": "Acme Bakery", "phone": "(512) 555-0100", "website": "https://acme.test", "offering": "We bake bread"}
LOCATION = {"title": "ACME Bakery LLC", "phoneNumbers": {"primaryPhone": "+1 512-555-0100"}, "websiteUri": "https://www.acme.test/",
            "profile": {"description": "We bake bread"}}


class CompareTests(unittest.TestCase):
    def test_reports_only_fields_that_differ_after_normalizing(self):
        found = compare.mismatches(LOCATION, PROFILE)
        self.assertEqual([(m["field"], m["current"], m["proposed"]) for m in found], [("title", "ACME Bakery LLC", "Acme Bakery")])
        self.assertEqual(compare.mismatches(LOCATION, {"business_name": "acme bakery llc", "offering": ""}), [])  # Blank profile fields are skipped.

    def test_location_matches_site_by_website_or_phone(self):
        self.assertTrue(compare.matches_site(LOCATION, PROFILE))
        self.assertTrue(compare.matches_site({"phoneNumbers": {"primaryPhone": "5125550100"}}, PROFILE))
        self.assertFalse(compare.matches_site({"websiteUri": "https://other.test"}, PROFILE))


class ClientTests(unittest.TestCase):
    def test_retries_once_on_401_after_renewing_and_never_on_other_errors(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request.get_header("Authorization"))
            if len(calls) == 1:
                raise HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"{}"))
            return io.BytesIO(b'{"ok": true}')
        with patch.object(api, "urlopen", urlopen):
            self.assertEqual(api.Client("old", lambda: "new").call("GET", "https://x.test"), {"ok": True})
        self.assertEqual(calls, ["Bearer old", "Bearer new"])
        with patch.object(api, "urlopen", side_effect=HTTPError("u", 403, "no", {}, io.BytesIO(b'{"error": {"message": "denied"}}'))):
            with self.assertRaisesRegex(api.ApiError, "denied"):
                api.Client("t").call("GET", "https://x.test")


class FakeGoogle:
    """Stands in for google.client.Client: serves a listing and records every write."""
    def __init__(self, location=None, claimed=True, fail=None):
        self.data, self.is_claimed, self.fail, self.writes = location or LOCATION, claimed, fail, []

    def locations(self):
        return [{**self.data, "name": "locations/1", "account": "accounts/9"}]

    def location(self, name):
        return self.data

    def claimed(self, name):
        return self.is_claimed

    def verifications(self, name):
        return []

    def verification_options(self, name):
        return [{"verificationMethod": "PHONE_CALL"}]

    def reviews(self, account, name):
        return [{"name": "accounts/9/locations/1/reviews/r1", "comment": "Great bread", "starRating": "FIVE"}]

    def questions(self, name):
        return [{"name": "locations/1/questions/q1", "text": "Open Sundays?"}]

    def write(self, *args):
        if self.fail:
            raise api.ApiError(self.fail)
        self.writes.append(args)

    def patch_location(self, *args):
        self.write("patch", *args)

    def reply_to_review(self, *args):
        self.write("reply", *args)

    def answer_question(self, *args):
        self.write("answer", *args)

    def start_verification(self, *args):
        self.write("verify", *args)
        return {"verification": {"state": "PENDING"}}


class GoogleCase(WebCase):
    def setUp(self):
        super().setUp()
        key = Fernet.generate_key().decode()
        env = patch.dict(os.environ, {"GOOGLE_OAUTH_CLIENT_ID": "id", "GOOGLE_OAUTH_CLIENT_SECRET": "secret", "GOOGLE_TOKEN_KEY": key,
                                      "GOOGLE_OAUTH_REDIRECT_URI": "http://127.0.0.1:8000/google/callback"})
        env.start()
        self.addCleanup(env.stop)
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        sync()
        self.ann = User.objects.create_user("ann")
        self.site = Site.objects.get()
        self.site.user, self.site.business_name, self.site.phone, self.site.offering = self.ann, "Acme Bakery", "(512) 555-0100", "We bake bread"
        self.site.save()
        self.client.force_login(self.ann)

    def connect(self, fake=None, claimed=True):
        self.fake = fake or FakeGoogle(claimed=claimed)
        self.conn = GoogleConnection(site=self.site, user=self.ann)
        proposals.save_tokens(self.conn, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
        self.loc = GoogleLocation.objects.create(connection=self.conn, account="accounts/9", location_id="locations/1")
        patcher = patch.object(proposals, "client_for", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.drafts = StubReport({"text": "Thanks for visiting!"})
        draft = patch.object(replies, "chat_model", return_value=self.drafts)
        draft.start()
        self.addCleanup(draft.stop)
        proposals.sync_site(self.site)


class OAuthTests(GoogleCase):
    def test_connect_checks_state_and_stores_tokens_encrypted(self):
        response = self.client.get(f"/google/connect/{self.site.pk}")
        self.assertIn("business.manage", response["location"])
        state = self.client.session["google_oauth"]["state"]
        self.assertIn(f"state={state}", response["location"])
        self.client.get("/google/callback?code=c&state=wrong")  # A forged callback stores nothing.
        self.assertFalse(GoogleConnection.objects.exists())
        self.client.get(f"/google/connect/{self.site.pk}")
        state = self.client.session["google_oauth"]["state"]
        tokens = {"access_token": "at-secret", "refresh_token": "rt-secret", "expires_in": 3600}
        with patch.object(oauth, "post", return_value=tokens) as post:
            self.client.get(f"/google/callback?code=abc&state={state}")
        self.assertEqual(post.call_args.args[1]["code"], "abc")
        conn = GoogleConnection.objects.get()
        self.assertNotIn("secret", conn.token + conn.refresh_token)
        self.assertEqual((oauth.decrypt(conn.token), oauth.decrypt(conn.refresh_token)), ("at-secret", "rt-secret"))
        self.client.post(f"/portal/local/{self.site.pk}/disconnect")
        conn.refresh_from_db()
        self.assertEqual((conn.token, conn.refresh_token, bool(conn.revoked_at)), ("", "", True))

    def test_only_the_owner_can_start_a_connection(self):
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.get(f"/google/connect/{self.site.pk}").status_code, 404)

    def test_a_refused_refresh_revokes_and_asks_for_a_reconnect(self):
        conn = GoogleConnection(site=self.site, user=self.ann)
        proposals.save_tokens(conn, {"access_token": "at", "refresh_token": "rt", "expires_in": -10})  # Already expired.
        with patch.object(oauth, "post", side_effect=HTTPError("u", 400, "invalid_grant", {}, io.BytesIO(b"{}"))):
            with self.assertRaisesRegex(api.ApiError, "Reconnect Google"):
                proposals.client_for(conn)
        self.assertIsNotNone(conn.revoked_at)


class PickTests(GoogleCase):
    def test_warns_when_neither_website_nor_phone_matches(self):
        fake = FakeGoogle(location={"title": "Other Co", "websiteUri": "https://other.test"})
        conn = GoogleConnection(site=self.site, user=self.ann)
        proposals.save_tokens(conn, {"access_token": "at", "refresh_token": "rt"})
        with patch.object(proposals, "client_for", return_value=fake), patch.object(proposals.replies, "chat_model", return_value=StubReport({"text": "t"})):
            self.assertContains(self.client.get("/portal/local"), "neither the website nor the phone matches")
            self.client.post(f"/portal/local/{self.site.pk}/pick", {"location": "locations/1"})
            self.assertFalse(GoogleLocation.objects.exists())
            self.client.post(f"/portal/local/{self.site.pk}/pick", {"location": "locations/1", "confirm": "1"})
        self.assertEqual(GoogleLocation.objects.get().location_id, "locations/1")


class ProposalTests(GoogleCase):
    def test_sync_only_queues_proposals(self):
        self.connect(claimed=False)
        kinds = sorted(Proposal.objects.filter(status="pending").values_list("kind", flat=True))
        self.assertEqual(kinds, ["claim_start", "field_edit", "qna_answer", "review_reply"])
        self.assertEqual(self.fake.writes, [])
        self.assertIn("Use only facts stated in the profile", self.drafts.messages[0][1])  # The last draft: the question's.
        self.assertIn("We bake bread", self.drafts.messages[1][1])
        proposals.sync_site(self.site)  # A second read updates, never duplicates.
        self.assertEqual(Proposal.objects.count(), 4)
        page = self.client.get("/portal/local")
        self.assertContains(page, "Acme Bakery")
        self.assertContains(page, "Thanks for visiting!")

    def test_approving_an_edit_writes_only_that_field_and_records_the_result(self):
        self.connect()
        edit = Proposal.objects.get(kind="field_edit")
        self.assertEqual((edit.before, edit.after), ({"value": "ACME Bakery LLC"}, {"value": "Acme Bakery"}))
        self.client.post(f"/portal/local/proposal/{edit.pk}/approve")
        edit.refresh_from_db()
        self.assertEqual(self.fake.writes, [("patch", "locations/1", "title", {"title": "Acme Bakery"})])
        self.assertEqual((edit.status, edit.decided_by), ("applied", self.ann))

    def test_a_rejected_proposal_never_writes_and_cannot_be_approved_later(self):
        self.connect()
        edit = Proposal.objects.get(kind="field_edit")
        self.client.post(f"/portal/local/proposal/{edit.pk}/reject")
        self.client.post(f"/portal/local/proposal/{edit.pk}/approve")
        edit.refresh_from_db()
        self.assertEqual((edit.status, self.fake.writes), ("rejected", []))
        with self.assertRaises(ValueError):
            proposals.apply(edit)

    def test_a_failed_write_is_recorded_and_the_listing_is_untouched(self):
        self.connect(FakeGoogle(fail="Quota exceeded"))
        edit = Proposal.objects.get(kind="field_edit")
        self.client.post(f"/portal/local/proposal/{edit.pk}/approve")
        edit.refresh_from_db()
        self.assertEqual((edit.status, edit.error), ("failed", "Quota exceeded"))

    def test_replies_post_only_after_approval_with_the_customers_edit(self):
        self.connect()
        reply = Proposal.objects.get(kind="review_reply")
        self.assertEqual((reply.status, reply.after), ("pending", {"text": "Thanks for visiting!"}))
        self.assertEqual(self.fake.writes, [])
        self.client.post(f"/portal/local/proposal/{reply.pk}/approve", {"text": "Thank you so much!"})
        self.assertEqual(self.fake.writes, [("reply", "accounts/9/locations/1/reviews/r1", "Thank you so much!")])

    def test_claim_starts_verification_only_when_approved(self):
        self.connect(claimed=False)
        claim = Proposal.objects.get(kind="claim_start")
        self.assertEqual(self.fake.writes, [])
        self.client.post(f"/portal/local/proposal/{claim.pk}/approve")
        claim.refresh_from_db()
        self.assertEqual((self.fake.writes, claim.status), ([("verify", "locations/1", "PHONE_CALL")], "applied"))

    def test_another_customer_cannot_decide_a_proposal(self):
        self.connect()
        edit = Proposal.objects.get(kind="field_edit")
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.post(f"/portal/local/proposal/{edit.pk}/approve").status_code, 404)
        self.assertEqual(self.fake.writes, [])
