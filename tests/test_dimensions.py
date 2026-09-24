import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from companyscan.dimensions import meta_ads as meta_ads_mod, reputation
from companyscan.dimensions.fonts import collect as fonts
from companyscan.dimensions.meta_ads import collect as meta_ads
from companyscan.dimensions.reputation import collect as llm_reputation
from companyscan.dimensions.security import collect as security
from companyscan.models import Response

ORIGIN = "https://acme.test"
DISCOVERY = {"origin": ORIGIN}


class Policy:
    def __init__(self, allowed=True):
        self.result = allowed

    def allowed(self, url):
        return self.result


class FakeClient:
    def __init__(self, bodies=None, allowed=True):
        self.bodies, self.fetched = bodies or {}, []
        self.policies = {ORIGIN: Policy(allowed)}
        self.config = SimpleNamespace(timeout=5)

    def get(self, url, allowed_origin=None):
        self.fetched.append(url)
        status, body = self.bodies.get(url, (404, ""))
        return Response(url, url, status=status, body=body)


class SecurityTest(unittest.TestCase):
    def test_missing_headers_mixed_content_and_cookies(self):
        pages = [
            {"url": f"{ORIGIN}/", "status": 200, "script_sources": ["http://cdn.test/a.js", "https://cdn.test/b.js"],
             "images": [{"url": "http://img.test/x.png"}, {"url": None}],
             "headers": {"set-cookie": "sid=1; Secure; SameSite=Lax", "server": "nginx",
                         "content-security-policy": "frame-ancestors 'none'"}},
            {"url": "http://acme.test/plain", "status": 200, "headers": {}},
            {"url": f"{ORIGIN}/gone", "status": 404, "headers": {}},
            {"url": f"{ORIGIN}/failed", "status": None},
        ]
        result = security(None, DISCOVERY, pages, "Acme")
        first, second = result["pages"]
        self.assertEqual(result["pages_checked"], 2)
        self.assertFalse(result["https"])
        self.assertIn("strict-transport-security", first["missing_headers"])
        self.assertNotIn("content-security-policy", first["missing_headers"])
        self.assertNotIn("x-frame-options/frame-ancestors", first["missing_headers"])  # CSP frame-ancestors covers it.
        self.assertEqual(first["mixed_content"], ["http://cdn.test/a.js", "http://img.test/x.png"])
        self.assertEqual(first["cookie_flags"], {"Secure": True, "HttpOnly": False, "SameSite": True})
        self.assertEqual(first["server"], "nginx")
        self.assertNotIn("strict-transport-security", second["missing_headers"])  # HSTS only applies to HTTPS.
        self.assertIn("x-frame-options/frame-ancestors", second["missing_headers"])
        self.assertIsNone(second["cookie_flags"])
        self.assertEqual(second["mixed_content"], [])
        self.assertIn({"header": "x-content-type-options", "pages": 2}, result["missing_summary"])

    def test_no_usable_pages_is_unknown_https(self):
        self.assertIsNone(security(None, DISCOVERY, [], "Acme")["https"])


class FontsTest(unittest.TestCase):
    def test_stylesheet_sources_and_page_families(self):
        google = "https://fonts.googleapis.com/css?family=Inter:400,700|Lora"
        typekit, third = "https://use.typekit.net/abc.css", "https://cdn.other.test/site.css"
        ok, broken = f"{ORIGIN}/main.css", f"{ORIGIN}/missing.css"
        client = FakeClient({ok: (200, "body{font-family:'Acme Sans',sans-serif}@font-face{font-family:\"Acme Sans\";src:url(a.woff)}")})
        pages = [{"url": f"{ORIGIN}/", "stylesheets": [google, typekit, third, ok, broken], "inline_font_families": ["Georgia"]},
                 {"url": f"{ORIGIN}/about", "stylesheets": [ok]},
                 {"url": f"{ORIGIN}/no-css"}]
        result = fonts(client, DISCOVERY, pages, "Acme")
        sheets = {s["url"]: s for s in result["stylesheets"]}
        self.assertEqual(sheets[google]["families"], ["Inter", "Lora"])
        self.assertEqual(sheets[typekit]["status"], "UNKNOWN")
        self.assertEqual(sheets[third]["status"], "NOT_FETCHED")
        self.assertEqual(sheets[ok]["families"], ["Acme Sans", "sans-serif"])
        self.assertEqual(sheets[ok]["font_faces"], ["Acme Sans"])
        self.assertEqual(sheets[broken]["families"], [])
        self.assertEqual(client.fetched, [ok, broken])  # Each stylesheet fetched once, third parties never.
        self.assertEqual(result["pages_checked"], 2)
        self.assertIn({"family": "Acme Sans", "pages": 2}, result["families"])
        self.assertIn({"family": "Inter", "pages": 1}, result["families"])
        self.assertIn("Georgia", result["pages"][0]["families"])

    def test_first_party_limit_and_robots_block_fetches(self):
        sheets = [f"{ORIGIN}/{n}.css" for n in range(3)]
        limited = FakeClient()
        result = fonts(limited, DISCOVERY, [{"url": ORIGIN, "stylesheets": sheets}], "Acme", limit=2)
        self.assertEqual(len(limited.fetched), 2)
        self.assertEqual(result["stylesheets"][2]["status"], "NOT_FETCHED")
        blocked = FakeClient(allowed=False)
        fonts(blocked, DISCOVERY, [{"url": ORIGIN, "stylesheets": sheets}], "Acme")
        self.assertEqual(blocked.fetched, [])


class MetaAdsTest(unittest.TestCase):
    def test_without_token_is_unknown(self):
        with patch.dict(os.environ, {}, clear=True):
            result = meta_ads(FakeClient(), DISCOVERY, [], "Acme")
        self.assertEqual((result["status"], result["reason"], result["countries"]), ("UNKNOWN", "no_token", ["US"]))

    def test_observed_ads_never_record_token(self):
        body = {"data": [{"page_name": "Acme"}, {"page_name": "Acme"}, {"page_name": "Other"}], "paging": {"next": "x"}}
        env = {"META_ACCESS_TOKEN": "secret-token", "META_AD_COUNTRIES": "GB,DE"}
        with patch.dict(os.environ, env, clear=True), patch.object(meta_ads_mod, "urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as call:
            result = meta_ads(FakeClient(), DISCOVERY, [], "Acme")
        self.assertIn("access_token=secret-token", call.call_args[0][0])
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(result["ad_count"], 3)
        self.assertTrue(result["more_available"])
        self.assertEqual(result["pages"], {"Acme": 2, "Other": 1})
        self.assertEqual(result["countries"], ["GB", "DE"])
        self.assertNotIn("secret-token", json.dumps(result))

    def test_api_and_network_errors_are_unknown(self):
        http = HTTPError("https://graph.facebook.com", 400, "Bad", {}, io.BytesIO(b'{"error":"bad token"}'))
        for error, reason, detail in ((http, "api_error", "bad token"), (URLError("offline"), "request_failed", "offline")):
            with patch.dict(os.environ, {"META_ACCESS_TOKEN": "t"}), patch.object(meta_ads_mod, "urlopen", side_effect=error):
                result = meta_ads(FakeClient(), DISCOVERY, [], "Acme")
            self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", reason))
            self.assertIn(detail, result["error"])


class StubChat:
    """Duck-types the LangChain chat model: plain answers, then structured output keyed by schema title."""
    STRUCTURED = {"ReputationAnalysis": {"recognized": True, "inferred_icp": "families", "inferred_location": "Toronto",
                                        "target_sentiment": 0.5, "competitors": []},
                  "BuyerPrompts": {"prompts": ["best family dentist in Toronto?"]},
                  "CompanyMentions": {"companies": [{"name": "Acme Dental", "website": None, "position": 1, "sentiment": 0.8},
                                                    {"name": "Beta", "website": None, "position": 2, "sentiment": 0.1}]}}

    def invoke(self, prompt):
        branded = prompt.startswith("What do you know")
        return SimpleNamespace(content="Acme Dental (acme.test) is a dentist" if branded else "Try Acme Dental or Beta.")

    def with_structured_output(self, schema):
        return SimpleNamespace(invoke=lambda prompt: self.STRUCTURED[schema["title"]])


class LlmReputationTest(unittest.TestCase):
    def test_ranks_through_the_reputation_model(self):
        with patch.object(reputation, "chat_model", return_value=StubChat()) as chat:
            result = llm_reputation(None, DISCOVERY, [], "Acme Dental")
        self.assertEqual(chat.call_args[0][0], reputation.REPUTATION_MODEL)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual((result["scores"]["rank"], result["scores"]["of"]), (1, 2))
        self.assertEqual(len(result["answers"]), 3)  # 1 generated question x 3 default samples.
        self.assertEqual(result["model"], reputation.REPUTATION_MODEL)
        self.assertTrue(result["branded"]["domain_mentioned"])
        self.assertIn("(Acme Dental)", result["branded"]["prompt"])
        self.assertTrue(result["limitations"])

    def test_model_failures_are_unknown(self):
        with patch.object(reputation, "chat_model", side_effect=Exception("missing OPENAI_API_KEY")):
            result = llm_reputation(None, DISCOVERY, [], "Acme Dental")
        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "llm_request_failed"))
        self.assertIn("OPENAI_API_KEY", result["error"])

if __name__ == "__main__":
    unittest.main()
