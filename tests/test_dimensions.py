import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from companyscan.dimensions import DIMENSIONS, coverage, google_business, meta_ads as meta_ads_mod, practitioners, reputation
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


class StubSearch:
    """A web-search chat model: answers come back as content blocks with url_citation annotations."""

    def __init__(self):
        self.tools, self.asked = None, []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, prompt):
        self.asked.append(prompt)
        answer = StubChat().invoke(prompt).content
        return SimpleNamespace(content=[{"type": "web_search_call", "id": "ws"}, {"type": "text", "text": answer, "annotations": [
            {"type": "url_citation", "url": "https://yelp.test/acme", "title": "Acme on Yelp"},
            {"type": "url_citation", "url": "https://yelp.test/acme", "title": "Acme on Yelp"}]}])


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

    def test_ai_search_answers_through_the_web_search_model(self):
        plain, search = StubChat(), StubSearch()
        with patch.object(reputation, "chat_model", side_effect=lambda name, **kw: search if name == reputation.SEARCH_MODEL else plain):
            result = DIMENSIONS["ai_search"]["collect"](None, DISCOVERY, [], "Acme Dental")
        self.assertEqual(search.tools, [{"type": "web_search"}])
        self.assertEqual(len(search.asked), 4)  # Branded + 1 question x 3 samples; plain writes the question and extracts.
        self.assertEqual((result["model"], result["extraction_model"]), (reputation.SEARCH_MODEL, reputation.REPUTATION_MODEL))
        self.assertEqual(result["scores"]["sources"][0], {"domain": "yelp.test", "citations": 3, "answers": 3, "is_target": False})
        self.assertEqual(result["branded"]["sources"], [{"url": "https://yelp.test/acme", "title": "Acme on Yelp"}])
        self.assertTrue(any(line.startswith("Answers use one model's web search") for line in result["limitations"]))
        self.assertFalse(any(line.startswith("No web search") for line in result["limitations"]))

    def test_reuses_the_previous_runs_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            older, newer = Path(tmp) / "older", Path(tmp) / "newer"
            (older / "technical").mkdir(parents=True)
            (older / "technical/ai_search.json").write_text(json.dumps({"status": "COMPLETE", "prompts": [{"text": "q old"}, "junk"]}))
            (newer / "technical").mkdir(parents=True)
            (newer / "technical/ai_search.json").write_text(json.dumps({"status": "UNKNOWN"}))  # Failed runs are skipped.
            client = SimpleNamespace(previous_runs=[newer, older], config=None)
            with patch.object(reputation, "chat_model", side_effect=lambda name, **kw: StubSearch() if name == reputation.SEARCH_MODEL else StubChat()):
                result = DIMENSIONS["ai_search"]["collect"](client, DISCOVERY, [], "Acme Dental")
                fresh = DIMENSIONS["llm_reputation"]["collect"](client, DISCOVERY, [], "Acme Dental")  # No llm_reputation file there.
        self.assertEqual(result["prompts"], [{"text": "q old", "source": "previous"}])
        self.assertEqual(result["questions_from"], "older")
        self.assertIsNone(fresh["questions_from"])
        self.assertEqual(fresh["prompts"][0]["source"], "generated")

    def test_model_failures_are_unknown(self):
        with patch.object(reputation, "chat_model", side_effect=Exception("missing OPENAI_API_KEY")):
            result = llm_reputation(None, DISCOVERY, [], "Acme Dental")
        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "llm_request_failed"))
        self.assertIn("OPENAI_API_KEY", result["error"])

class StubJudge:
    """Answers answer_coverage's structured calls by schema title; a Coverage prompt about "wait" fails."""

    def __init__(self):
        self.judged = []

    def with_structured_output(self, schema):
        def invoke(prompt):
            title = schema["title"]
            if title == "SiteIdentity":
                return {"category": "dentist", "offerings": ["braces", "cleanings"], "site_icp": "families", "evidence": []}
            if title == "BuyerQuestions":
                return {"questions": [{"question": q, "offering": "braces", "intent": i} for q, i in
                                      (("What do braces cost?", "cost"), ("Do you see kids on Saturday?", "availability"),
                                       ("What is the wait for braces?", "bogus"), ("What do braces cost?", "cost"))]}
            if title == "CandidatePages":
                return {"matches": [{"question_number": 1, "urls": ["https://acme.test/braces", "https://acme.test/braces"]},
                                    {"question_number": 2, "urls": ["https://elsewhere.test/"]},
                                    {"question_number": 3, "urls": ["https://acme.test/braces"]}]}
            self.judged.append(prompt)
            if "wait" in prompt:
                raise RuntimeError("rate limited")
            return {"coverage": "answered", "best_url": "https://acme.test/braces", "quote": "Braces   cost $5,000", "gap": None}
        return SimpleNamespace(invoke=invoke)


class AnswerCoverageTest(unittest.TestCase):
    PAGES = [{"url": "https://acme.test/", "title": "Acme", "visible_text": "Welcome to Acme"},
             {"url": "https://acme.test/braces", "title": "Braces", "headings": [{"level": 1, "text": "Braces"}],
              "visible_text": "Braces cost $5,000 to $7,000."},
             {"url": "https://acme.test/copy", "visible_text": "Welcome", "duplicate_of": "https://acme.test/"}]

    def test_judges_candidates_and_records_gaps(self):
        llm = StubJudge()
        result = coverage.check_coverage(llm, "acme.test", self.PAGES)
        rows = {q["question"]: q for q in result["questions"]}
        self.assertEqual(len(rows), 3)  # The repeated question is asked once.
        self.assertEqual(len(llm.judged), 2)  # The question whose only candidate isn't crawled is missing without a call.
        cost = rows["What do braces cost?"]
        self.assertEqual((cost["coverage"], cost["best_url"], cost["verified"]), ("answered", "https://acme.test/braces", True))
        self.assertEqual(cost["candidates"], ["https://acme.test/braces"])
        self.assertEqual((rows["Do you see kids on Saturday?"]["coverage"], rows["Do you see kids on Saturday?"]["candidates"]), ("missing", []))
        wait = rows["What is the wait for braces?"]
        self.assertEqual((wait["coverage"], wait["intent"], wait["error"]), (None, "other", "rate limited"))
        self.assertEqual(result["summary"], {"answered": 1, "partial": 0, "missing": 1, "failed": 1, "questions": 3})
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIn("untrusted page content", llm.judged[0])

    def test_reused_questions_skip_the_site_read(self):
        llm = StubJudge()
        result = coverage.check_coverage(llm, "acme.test", self.PAGES,
                                         questions=[{"question": "What do braces cost?", "offering": "braces", "intent": "cost"}])
        self.assertEqual(result["site_read"]["pages"], [])
        self.assertEqual([q["question"] for q in result["questions"]], ["What do braces cost?"])
        self.assertEqual(len(llm.judged), 1)

    def test_no_page_text_and_model_failure_are_unknown(self):
        self.assertEqual(coverage.check_coverage(StubJudge(), "acme.test", [])["reason"], "no_page_text")
        with patch.object(coverage, "chat_model", side_effect=Exception("missing OPENAI_API_KEY")):
            result = DIMENSIONS["answer_coverage"]["collect"](None, DISCOVERY, self.PAGES, "Acme")
        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "llm_request_failed"))
        self.assertTrue(result["limitations"])


class StubRoster:
    """Returns a fixed practitioner read for the Practitioners schema and records the prompt."""

    def __init__(self, practitioners):
        self.practitioners, self.prompts = practitioners, []

    def with_structured_output(self, schema):
        return SimpleNamespace(invoke=lambda prompt: self.prompts.append(prompt) or {"practitioners": self.practitioners})


def person(name, url, dedicated, **fields):
    return {"name": name, "role": "Dentist", **{f: fields.get(f, []) for f in practitioners.FIELDS},
            "profile_url": url, "dedicated_page": dedicated, "evidence": fields.get("evidence", [])}


def ld(*objs):
    return {"documents": [{"@graph": list(objs)}]}


class PractitionersTest(unittest.TestCase):
    PAGES = [{"url": "https://acme.test/", "visible_text": "Welcome", "classification": {"label": "homepage"}},
             {"url": "https://acme.test/our-team/", "visible_text": "Dr. Jane Smith, DDS\nDr. Bo Lee",
              "json_ld": ld({"@type": "Dentist", "name": "Acme", "employee": {"@type": "Person", "name": "Jane Smith",
                                                                               "jobTitle": "Dentist", "sameAs": ["https://linkedin.test/jane", 7]}})},
             {"url": "https://acme.test/dr-jane-smith", "visible_text": "Dr. Jane Smith trained at Western."},
             {"url": "https://acme.test/services/pediatric-dentistry", "visible_text": "Kids"},
             *({"url": f"https://acme.test/blog/{i}", "visible_text": "Post", "json_ld": ld({"@type": "Person", "name": "Acme Admin"})}
               for i in range(4))]

    def test_profiles_schema_and_dedicated_pages(self):
        llm = StubRoster([
            person("Dr. Jane Smith, DDS", "http://www.acme.test/dr-jane-smith/", True, credentials=["DDS"], education=["Western"],
                   evidence=[{"url": "https://acme.test/dr-jane-smith", "quote": "trained  at Western", "supports": "education"}]),
            person("Dr. Bo Lee", None, True, evidence=[{"quote": "Dr. Bo Lee", "supports": "name"}]),  # The model dropped the URL.
            person("Dr. Al Ng", "https://acme.test/our-team/", True, evidence=[{"url": "https://acme.test/our-team/", "quote": "invented", "supports": "x"}])])
        result = practitioners.check_practitioners(llm, "acme.test", self.PAGES)
        rows = {r["name"]: r for r in result["practitioners"]}
        jane, bo, al = rows["Dr. Jane Smith, DDS"], rows["Dr. Bo Lee"], rows["Dr. Al Ng"]
        self.assertEqual(jane["profile_url"], "https://acme.test/dr-jane-smith")  # The model's URL, matched to the crawl.
        self.assertTrue(jane["checks"]["dedicated_page"] and jane["checks"]["person_schema"] and jane["checks"]["same_as"])
        self.assertEqual(jane["person_schema"]["same_as"], ["https://linkedin.test/jane"])
        self.assertTrue(jane["evidence"][0]["verified"])
        self.assertEqual(bo["profile_url"], "https://acme.test/our-team/")  # Falls back to the page its quote was found on.
        self.assertTrue(bo["evidence"][0]["verified"])
        self.assertFalse(bo["checks"]["dedicated_page"] or al["checks"]["dedicated_page"])  # Shared team page.
        self.assertFalse(al["evidence"][0]["verified"])
        self.assertEqual([s["name"] for s in result["schema_people_unmatched"]], ["Acme Admin"])
        self.assertEqual(result["summary"], {"practitioners": 3, "with_dedicated_page": 1, "with_person_schema": 1,
                                             "with_same_as": 1, "with_credentials": 1})
        self.assertIn("=== https://acme.test/our-team/", llm.prompts[0])
        self.assertNotIn("pediatric-dentistry", llm.prompts[0])  # "dentistry" isn't a people word.
        self.assertNotIn("/blog/", llm.prompts[0])  # Author markup on every post doesn't make them people pages.

    def test_name_matching_ignores_titles(self):
        self.assertTrue(practitioners.same_person("Dr. Poonam Sekhon, DDS, MSc", "Poonam Sekhon"))
        self.assertFalse(practitioners.same_person("Dr. Smith", "Jane Smith"))  # One shared word is too weak.

    def test_unknown_without_pages_or_model(self):
        self.assertEqual(practitioners.check_practitioners(StubRoster([]), "acme.test", [])["reason"], "no_page_text")
        with patch.object(practitioners, "chat_model", side_effect=Exception("missing OPENAI_API_KEY")):
            result = DIMENSIONS["practitioners"]["collect"](None, DISCOVERY, self.PAGES, "Acme")
        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "llm_request_failed"))


PLACE = {"displayName": {"text": "Acme Dental Centre"}, "formattedAddress": "12 Main St, Guelph, ON N1H 1G5",
         "addressComponents": [{"longText": "12", "types": ["street_number"]}, {"longText": "N1H 1G5", "types": ["postal_code"]}],
         "nationalPhoneNumber": "(519) 555-0100", "websiteUri": "https://www.acme.test/?utm=gbp", "primaryType": "dentist",
         "businessStatus": "OPERATIONAL", "rating": 4.8, "userRatingCount": 212,
         "regularOpeningHours": {"weekdayDescriptions": ["Monday: 9 AM–5 PM"]},
         "reviews": [{"rating": 5, "publishTime": "2026-08-01T00:00:00Z", "text": {"text": "Great dentist!"},
                      "authorAttribution": {"displayName": "Pat Q"}},
                     {"rating": 5, "publishTime": "2026-09-01T00:00:00Z", "text": {"text": " ".join(["word"] * 25)}}]}
NAMESAKE = {"displayName": {"text": "Acme Dental"}, "websiteUri": "https://other.test/", "nationalPhoneNumber": "(416) 555-9999"}
SITE = [{"url": ORIGIN + "/", "visible_text": "Visit us at 12 Main St, Guelph ON n1h1g5",
         "json_ld": {"documents": [{"@type": "Dentist", "name": "Acme Dental", "telephone": "+1 519-555-0100"}]}}]


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GoogleBusinessTest(unittest.TestCase):
    def run_with(self, places, env=True):
        sent = []

        def fake(request, timeout):
            sent.append(request)
            return Reply(json.dumps({"places": places}).encode())
        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "secret-key"} if env else {}, clear=not env), \
                patch.object(google_business, "urlopen", fake):
            return DIMENSIONS["google_business"]["collect"](None, DISCOVERY, SITE, "Acme Dental"), sent

    def test_matches_the_listing_and_compares_it(self):
        result, sent = self.run_with([NAMESAKE, PLACE])
        self.assertTrue(result["found"])
        self.assertEqual(result["matched_by"], "website")  # The namesake listed first is skipped.
        agrees = {c["field"]: c["agrees"] for c in result["checks"]}
        self.assertEqual(agrees, {"name": "variant", "phone": True, "website": True, "postal_code": True, "street_number": True, "category": None})
        self.assertEqual(result["mismatches"], [])
        r = result["reviews"]
        self.assertEqual((r["rating"], r["count"], r["sample"], r["sample_detailed"], r["sample_latest"]), (4.8, 212, 2, 1, "2026-09-01T00:00:00Z"))
        self.assertNotIn("Pat Q", json.dumps(result))  # Reviewer names aren't stored.
        self.assertNotIn("secret-key", json.dumps(result))
        self.assertEqual(sent[0].get_header("X-goog-api-key"), "secret-key")
        self.assertEqual(json.loads(sent[0].data)["textQuery"], "Acme Dental")

    def test_phone_match_and_mismatches(self):
        moved = {**PLACE, "websiteUri": "https://acme-dental.example/", "addressComponents": [{"longText": "K2P 2A1", "types": ["postal_code"]}]}
        result, _ = self.run_with([moved])
        self.assertEqual(result["matched_by"], "phone")
        self.assertEqual(result["mismatches"], ["website", "postal_code"])

    def test_no_matching_listing_is_not_found(self):
        result, _ = self.run_with([NAMESAKE])
        self.assertEqual((result["status"], result["found"]), ("OBSERVED", False))
        self.assertEqual(result["candidates"][0]["matched_by"], None)
        self.assertNotIn("checks", result)

    def test_unknown_without_key_or_on_api_error(self):
        result, sent = self.run_with([], env=False)
        self.assertEqual((result["status"], result["reason"], sent), ("UNKNOWN", "no_key", []))
        error = HTTPError(google_business.URL, 403, "Forbidden", {}, io.BytesIO(b"API not enabled"))
        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "k"}), patch.object(google_business, "urlopen", side_effect=error):
            result = DIMENSIONS["google_business"]["collect"](None, DISCOVERY, SITE, "Acme Dental")
        self.assertEqual((result["reason"], result["error"]), ("api_error", "API not enabled"))


if __name__ == "__main__":
    unittest.main()
