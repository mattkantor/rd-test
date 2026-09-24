import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from companyscan.web.dashboard import MISSING, UNREADABLE, describe, link, load, read, table

SCORED = {
    "status": "COMPLETE", "domain": "acme.test", "error": None,
    "branded": {"raw_answer": "Acme Dental is a dentist.", "domain_mentioned": True},
    "prompts": [{"text": "best dentist?", "source": "generated"}],
    "answers": [{"prompt": "best dentist?", "sample": 1, "raw_answer": "Try Acme Dental or Beta.",
                 "companies": [{"name": "Acme Dental"}, {"name": "Beta"}, "junk"], "error": None}],
    "scores": {"rank": 1, "of": 2, "mention_rate": 1.0, "share_of_voice": 0.5, "answers_scored": 1, "answers_total": 1,
               "leaderboard": [{"company": "Acme Dental", "key": "acme.test", "mentions": 1, "avg_position": 1.0, "is_target": True},
                               {"company": "Beta", "key": "beta", "mentions": 1, "avg_position": 2.0, "is_target": False}],
               "sentiment": {"score": 42, "n": 2, "min": 20, "max": 60,
                             "branded": {"score": 60, "n": 1, "min": 60, "max": 60},
                             "unbranded": {"score": 20, "n": 1, "min": 20, "max": 20}}},
    "model": ["claude-x"], "limitations": ["one sample"],
}
LEGACY = {"raw_answer": "Acme is a dentist.", "domain_mentioned": True,
          "analysis": {"competitors": [{"name": "Beta", "website": "beta.test", "reason": "same city"}]}}


def write(d, rel, value):
    path = d / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    return rel


def full_bundle(root, name="acme", reputation=SCORED):
    d = Path(root) / name
    files = [
        write(d, "pages/0001.json", {"id": "0001", "url": "https://acme.test/", "status": 200, "classification": {"label": "homepage"},
                                     "title": "Acme home", "depth": 0, "ctas": [{"text": "Book"}], "extraction_status": "EXTRACTED",
                                     "content_path": "content/homepage.md", "visible_text": "Welcome to Acme Dental family care",
                                     "meta_description": "Family dentistry in Toronto.", "canonical_url": "https://acme.test/",
                                     "headings": [{"level": 1, "text": "Care for Toronto families"}],
                                     "json_ld": {"types": ["Dentist"], "errors": [],
                                                 "issues": [{"severity": "warning", "message": "Dentist is missing recommended 'telephone'"}]},
                                     "measurement": [{"tool": "Google tag"}],
                                     "accessibility": {"findings": [{"rule_id": "image-alt", "message": "Image has no alt text",
                                                                     "wcag": {"criterion": "1.1.1"}},
                                                                    {"rule_id": "button-name", "message": "<img src=x onerror=alert(1)>",
                                                                     "wcag": {"criterion": "4.1.2"}}]}}),
        write(d, "pages/0002.json", {"id": "0002", "url": "javascript:alert(1)", "status": 404, "classification": {"label": "other"},
                                     "title": "Broken page", "depth": 2, "ctas": [], "extraction_status": "FAILED"}),
        write(d, "pages/0003.json", {"id": "0003", "url": "https://acme.test/about", "status": 200, "classification": {"label": "about"},
                                     "title": "About us", "depth": 1, "ctas": [], "extraction_status": "EXTRACTED",
                                     "content_path": "../../../etc/passwd", "visible_text": "About Acme",
                                     "canonical_url": "https://acme.test/", "headings": [{"level": 1, "text": "About"}, {"level": 1, "text": "Team"}],
                                     "json_ld": {}, "measurement": [], "accessibility": {"findings": []}}),
        write(d, "content/homepage.md", "# Acme"),
        write(d, "technical/robots.json", {"status": 200, "policy_status": "OBSERVED", "text": "User-agent: *\nAllow: /"}),
        write(d, "technical/aeo.json", {"pages_checked": 3, "pages_with_json_ld": 2, "types": {"Dentist": 2},
                                        "issue_summary": [{"severity": "warning", "code": "missing_recommended", "pages": 2}]}),
        write(d, "technical/measurement.json", {"tools": [{"tool": "Google tag", "category": "analytics", "ids": ["G-1"]}],
                                                "has_measurement": True, "has_consent_tool": False}),
        write(d, "technical/social-preview.json", {"pages_checked": 3, "issue_summary": [], "pages": [
            {"url": "https://acme.test/", "issues": []},
            {"url": "https://acme.test/about", "issues": [{"severity": "warning", "code": "missing_image", "tag": "og:image"}]}]}),
        write(d, "technical/indexing.json", [{"url": "https://acme.test/about", "noindex_observed": True, "extractability": "PASS"}]),
        write(d, "technical/redirects.json", []),
        write(d, "technical/accessibility.json", {
            "automated_status": "WARNING", "conformance_status": "UNKNOWN", "pages_checked": 3, "finding_count": 1,
            "findings": [{"rule_id": "image-alt", "severity": "WARNING", "url": "https://acme.test/",
                          "wcag": {"criterion": "1.1.1", "level": "A"}, "evidence": {"line": 3, "html": "<img src=x onerror=alert(1)>"}}]}),
        write(d, "technical/security.json", {"pages_checked": 3, "https": True,
                                             "missing_summary": [{"header": "content-security-policy", "pages": 3}],
                                             "pages": [{"url": "https://acme.test/", "https": True,
                                                        "missing_headers": ["content-security-policy"], "mixed_content": []}]}),
        write(d, "technical/fonts.json", {"distinct_families": 2, "families": [{"family": "Inter", "pages": 3}]}),
        write(d, "technical/llm_reputation.json", reputation),
        write(d, "social/discovered.json", {"profiles": [{"network": "linkedin", "url": "https://www.linkedin.com/company/acme",
                                                          "evidence": [{"source": "https://acme.test/"}]}]}),
        write(d, "company.json", {"names": [{"value": "Acme Dental", "kind": "EXTRACTED", "source": "https://acme.test/"}]}),
        write(d, "urls.json", {"skipped": [{"url": "https://acme.test/cart", "reason": "excluded_path"}]}),
    ]
    artifacts = [{"path": f, "sha256": hashlib.sha256((d / f).read_bytes()).hexdigest()} for f in files]
    write(d, "manifest.json", {"input_url": "https://acme.test/", "created_at": "2026-09-23T12:00:00+00:00", "status": "PARTIAL",
                               "command": "scan", "config": {"max_pages": 50, "max_depth": 3,
                                                             "dimensions": ["security", "fonts", "llm_reputation"]},
                               "counts": {"pages": 3, "extracted_pages": 2, "profiles": 1, "skipped": 1},
                               "errors": [{"url": "https://acme.test/x", "error": "timeout"}],
                               "artifacts": artifacts, "limitations": ["Public HTML only"]})
    write(d, "analysis/report.md", "# Acme report")
    write(d, "analysis/analysis.json", {"findings": [{"id": "F1", "severity": "WARNING", "title": "Thin proof"}]})
    return d


class HelperTest(unittest.TestCase):
    def test_read_missing_and_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp), "bad.json", "{nope")
            write(Path(tmp), "good.json", {"a": 1})
            self.assertEqual(read(tmp, "absent.json"), MISSING)
            self.assertEqual(read(tmp, "bad.json"), UNREADABLE)
            self.assertEqual(read(tmp, "good.json"), {"a": 1})

    def test_link_allows_only_web_urls(self):
        self.assertEqual(link("https://acme.test/x"), "https://acme.test/x")
        self.assertEqual(link(" http://acme.test "), "http://acme.test")
        for bad in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x", "http://[bad", "/relative", 42, None):
            self.assertIsNone(link(bad), bad)

    def test_table_flattens_one_level_and_limits_rows(self):
        items = [{"rule": "alt", "wcag": {"criterion": "1.1.1"}, "evidence": [1, 2], "deep": {"a": {"b": 1}}}] * 3 + ["junk"]
        t = table(items, limit=2)
        self.assertEqual(t["columns"], ["rule", "wcag.criterion", "evidence", "deep"])
        self.assertEqual(t["rows"][0], ["alt", "1.1.1", "2 items", "1 fields"])
        self.assertEqual((t["shown"], t["total"]), (2, 4))
        self.assertEqual(table(None), {"columns": [], "rows": [], "total": 0, "shown": 0})

    def test_describe_splits_fields_text_and_tables(self):
        d = describe({"a": 1, "text": "hi", "tools": [{"x": 1}], "types": {"Dentist": 2}, "ids": ["G-1"], "empty": [],
                      "nested": {"k": {"z": 1}}})
        self.assertEqual(d["fields"], {"a": 1, "ids": "G-1", "empty": "none", "nested": "1 fields"})
        self.assertEqual(d["text"], "hi")
        self.assertEqual([name for name, _ in d["tables"]], ["tools", "types"])
        self.assertEqual(describe([{"u": 1}])["tables"][0][0], "items")
        self.assertEqual(describe(MISSING)["state"], MISSING)


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundle = full_bundle(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_header_integrity_report_tiles_and_anomalies(self):
        m = load(self.bundle)
        self.assertEqual((m["header"]["host"], m["header"]["status"], m["header"]["errors"]), ("acme.test", "PARTIAL", 1))
        self.assertEqual(m["integrity"], [])
        self.assertEqual(m["report"]["findings"], [{"id": "F1", "verdict": "WARNING", "title": "Thin proof"}])
        self.assertEqual(m["report"]["md"].name, "report.md")
        tiles = {t["title"]: (t["value"], t["sub"], t["level"], t["status"], t["meter"]) for t in m["tiles"]}
        self.assertEqual(list(tiles), ["Pages crawled", "Report", "Accessibility (WCAG)", "Analytics", "SEO basics", "AEO structured data",
                                       "Social previews", "Security headers", "Fonts", "AI reputation"])  # No Meta ads: not collected.
        self.assertEqual(tiles["Pages crawled"], (3, "of 50 limit · 1 skipped", "warning", "PARTIAL", {"pct": 6}))
        self.assertEqual((tiles["Report"][0], tiles["Report"][2], tiles["Report"][3]), (1, "warning", "1 WARNING"))
        self.assertEqual(tiles["AEO structured data"], ("67%", "pages with JSON-LD · 1 issue type", "warning", "1 issue type", {"pct": 67}))
        self.assertEqual(tiles["Security headers"],
                         ("5/6", "headers present on every page · most missing: content-security-policy", "warning", "HTTPS",
                          {"pct": 83}))
        self.assertEqual(tiles["Fonts"][:3], (1, "named family · most used: Inter", "good"))
        self.assertEqual(tiles["SEO basics"][:4], (1, "of 2 pages pass title, description, H1 and canonical checks", "warning",
                                                   "1 page to fix"))
        self.assertEqual({t["title"]: t["href"] for t in m["tiles"]}["Accessibility (WCAG)"], "?sort=accessibility#pages")
        self.assertEqual(tiles["AI reputation"],
                         ("#1", "of 2 companies · named in 100% of buyer answers", "good", "Sentiment +42", {"pct": 100}))
        self.assertEqual([(a["level"], a["text"]) for a in m["attention"]], [
            ("serious", "1 page failed to load"),
            ("warning", "1 WARNING finding in the report"),
            ("warning", "1 security header missing (most: content-security-policy, 3 pages)"),
            ("warning", "1 potential accessibility barrier (WCAG 2.2)"),
            ("warning", "Analytics runs without a detected consent tool"),
            ("warning", "1 page with SEO issues (title, description, H1 or canonical)"),
            ("warning", "1 structured-data issue type"),
        ])
        board = m["reputation"]["scores"]["leaderboard"]
        self.assertEqual([r["width"] for r in board], [100, 100])
        self.assertEqual(m["reputation"]["scores"]["diverging"], {"left": 50, "width": 21.0, "sign": "pos"})

    def test_sections(self):
        m = load(self.bundle)
        site = {c["title"]: c for c in m["site"]}
        self.assertEqual(list(site), ["robots.txt", "Sitemap", "AI crawler access", "llms.txt", "Redirects", "Fonts"])
        self.assertEqual((site["robots.txt"]["level"], site["robots.txt"]["status"], site["robots.txt"]["text"]),
                         ("good", "Crawling rules found", "User-agent: *\nAllow: /"))
        self.assertEqual((site["Sitemap"]["status"], site["Sitemap"]["file"]), ("Not collected", None))
        self.assertEqual(site["Fonts"]["table"]["rows"], [["Inter", 3]])
        self.assertEqual((m["meta_ads"]["title"], m["meta_ads"]["status"]), ("Meta Ad Library", "Not collected"))
        self.assertEqual(m["profiles"][0]["network"], "linkedin")
        self.assertEqual((m["names"][0]["value"], m["names"][0]["pages"]), ("Acme Dental", 1))
        self.assertEqual(m["reputation"]["scores"]["rank"], 1)
        self.assertEqual(m["reputation"]["questions"][0]["answers"][0]["named"], "Acme Dental, Beta")
        self.assertEqual((m["coverage"]["reasons"], m["coverage"]["skipped"]["total"]), ([("excluded_path", 1)], 1))
        self.assertEqual(m["coverage"]["limitations"], ["Public HTML only"])
        self.assertIn("technical/security.json", m["coverage"]["raw"])

    def test_site_cards_flag_problems(self):
        write(self.bundle, "technical/robots.json", {"status": None, "error": "timeout", "policy_status": "UNKNOWN"})
        write(self.bundle, "technical/crawler-access.json", {"checks": [
            {"agent": "GPTBot", "urls": [{"robots_allowed": False}, {"robots_allowed": True}]},
            {"agent": "ClaudeBot", "urls": [{"robots_allowed": True}]}]})
        write(self.bundle, "technical/redirects.json", [{"url": "http://acme.test/a", "final_url": "https://acme.test/b",
                                                         "chain": [{}, {}], "error": None}])
        write(self.bundle, "technical/meta_ads.json", {"status": "OBSERVED", "ad_count": 2, "countries": ["GB"],
                                                       "pages": {"Acme": 2}, "ads": []})
        m = load(self.bundle)
        site = {c["title"]: (c["level"], c["status"]) for c in m["site"]}
        self.assertEqual(site["robots.txt"], ("serious", "Unknown: page crawl stopped"))
        self.assertEqual(site["AI crawler access"], ("warning", "1 AI bot blocked on some pages"))
        self.assertEqual(site["Redirects"], ("warning", "1 chain with several hops or errors"))
        self.assertEqual((m["meta_ads"]["level"], m["meta_ads"]["status"], m["meta_ads"]["table"]["rows"]),
                         ("good", "2 ads found", [["Acme", 2]]))

    def test_page_cards_group_every_check_by_page(self):
        cards = {c["id"]: c for c in load(self.bundle)["pages"]}
        home = {a["name"]: (a["level"], a["summary"]) for a in cards["0001"]["areas"]}
        self.assertEqual(home, {
            "Content": ("good", "HTTP 200 · 6 words · 1 CTA"),
            "SEO": ("good", "Title, description, H1 and canonical look right"),
            "AEO": ("warning", "Dentist is missing recommended 'telephone'"),
            "Social": ("good", "Preview tags look right"),
            "Accessibility": ("warning", "image-alt (WCAG 1.1.1): Image has no alt text (+1 more)"),
            "Analytics": ("good", "Google tag"),
            "Security": ("warning", "1 security header missing"),
        })
        self.assertEqual((cards["0001"]["level"], cards["0001"]["issues"], cards["0001"]["path"]), ("warning", 4, "/"))
        about = {a["name"]: a for a in cards["0003"]["areas"]}
        self.assertEqual(about["SEO"]["details"][:4], ["No meta description", "2 H1 headings", "Marked noindex",
                                                       "Canonical points to https://acme.test/"])
        self.assertEqual((about["AEO"]["level"], about["AEO"]["summary"]), ("neutral", "No structured data (JSON-LD)"))
        self.assertEqual(about["Social"]["summary"], "og:image: missing image")
        self.assertEqual(about["Analytics"]["summary"], "No analytics tag in the server HTML")
        self.assertEqual(about["Security"]["level"], "neutral")  # Not in the security report: shown as unchecked, not passed.
        broken = {a["name"]: a for a in cards["0002"]["areas"]}
        self.assertEqual((broken["Content"]["level"], broken["Content"]["summary"]), ("critical", "HTTP 404 (+1 more)"))
        self.assertEqual({broken[n]["level"] for n in ("SEO", "AEO", "Social")}, {"neutral"})

    def test_page_card_sorting_and_safe_content_links(self):
        write(self.bundle, "pages/0004.json", "{corrupt")
        ids = lambda m: [p["id"] for p in m["pages"]]
        m = load(self.bundle)
        self.assertEqual(ids(m), ["0002", "0004", "0003", "0001"])  # Critical first, then by issue count (6 before 4).
        self.assertEqual((m["pages"][2]["content"], m["pages"][3]["content"]), (None, "content/homepage.md"))  # ../ dropped.
        self.assertEqual((m["pages"][1]["label"], m["pages"][1]["level"]), (UNREADABLE, "critical"))
        self.assertEqual(ids(load(self.bundle, "path")), ["0001", "0003", "0004", "0002"])
        self.assertEqual(ids(load(self.bundle, "seo"))[:2], ["0003", "0001"])  # Worst SEO first.
        self.assertEqual(ids(load(self.bundle, "path", desc=True))[0], "0002")
        bogus = load(self.bundle, "bogus")
        self.assertEqual((ids(bogus), bogus["sort"]), (ids(m), "issues"))

    def test_content_paths_are_normalized_inside_the_bundle(self):
        write(self.bundle, "pages/0004.json", {"id": "0004", "content_path": str((self.bundle / "content/homepage.md").resolve())})
        write(self.bundle, "pages/0005.json", {"id": "0005", "content_path": "content/../content/homepage.md"})
        write(self.bundle, "pages/0006.json", {"id": "0006", "content_path": "content/x\u0000y.md"})
        content = {p["id"]: p["content"] for p in load(self.bundle)["pages"]}
        self.assertEqual((content["0004"], content["0005"], content["0006"]), ("content/homepage.md", "content/homepage.md", None))

    def test_anomalies_for_bad_signals(self):
        write(self.bundle, "technical/security.json", {"https": False, "missing_summary": []})
        write(self.bundle, "technical/aeo.json", {"pages_checked": 3, "pages_with_syntax_errors": ["https://acme.test/"]})
        scores = {**SCORED["scores"], "rank": None, "sentiment": {**SCORED["scores"]["sentiment"], "score": -30}}
        write(self.bundle, "technical/llm_reputation.json", {**SCORED, "scores": scores})
        levels = {a["text"]: a["level"] for a in load(self.bundle)["attention"]}
        self.assertEqual(levels["Not every page is served over HTTPS"], "critical")
        self.assertEqual(levels["JSON-LD syntax errors on 1 page"], "serious")
        self.assertEqual(levels["Not named in any AI buyer answer"], "serious")
        self.assertEqual(levels["Negative AI sentiment (-30)"], "serious")
        self.assertEqual(list(levels.values())[0], "critical")  # Most severe first.
        m = load(self.bundle)
        self.assertEqual(m["reputation"]["scores"]["diverging"], {"left": 35.0, "width": 15.0, "sign": "neg"})

    def test_generic_font_keywords_do_not_count(self):
        families = [{"family": f, "pages": 3} for f in ("sans-serif", "Archivo", "Helvetica Neue", "Arial", "inherit", "system-ui")]
        write(self.bundle, "technical/fonts.json", {"distinct_families": 6, "families": families})
        m = load(self.bundle)
        self.assertEqual({t["title"]: t["value"] for t in m["tiles"]}["Fonts"], 3)
        self.assertNotIn("#site", [a["href"] for a in m["attention"] if "font" in a["text"]])
        many = [{"family": f"Font {i}", "pages": 1} for i in range(5)]
        write(self.bundle, "technical/fonts.json", {"families": many})
        self.assertIn(("warning", "5 named font families declared"), [(a["level"], a["text"]) for a in load(self.bundle)["attention"]])

    def test_standalone_reputation_run_fills_in(self):
        (self.bundle / "technical/llm_reputation.json").unlink()
        root = self.bundle.parent

        def run(name, host, created, rank):
            d = root / name
            write(d, "manifest.json", {"command": "reputation", "input_url": host, "created_at": created, "status": "COMPLETE",
                                       "model": "claude-x"})
            write(d, "reputation/reputation.json", SCORED["branded"])
            write(d, "reputation/answers.json", {"prompts": SCORED["prompts"], "answers": SCORED["answers"]})
            write(d, "reputation/scores.json", {**SCORED["scores"], "rank": rank})

        run("acme.test-reputation-old", "acme.test", "2026-09-01T00:00:00+00:00", 2)
        run("acme.test-reputation-new", "www.acme.test", "2026-09-20T00:00:00+00:00", 1)
        run("other.test-reputation", "other.test", "2026-09-30T00:00:00+00:00", 5)  # Different site: ignored.
        m = load(self.bundle)
        self.assertEqual((m["reputation"]["scores"]["rank"], m["reputation"]["source"]["dir"]), (1, "acme.test-reputation-new"))
        self.assertIn("AI reputation", [t["title"] for t in m["tiles"]])
        (self.bundle / "technical").mkdir(exist_ok=True)
        write(self.bundle, "technical/llm_reputation.json", {**SCORED, "scores": {**SCORED["scores"], "rank": 2}})
        self.assertEqual((load(self.bundle)["reputation"]["scores"]["rank"], load(self.bundle)["reputation"]["source"]),
                         (2, None))  # The crawl's own result wins.

    def test_integrity_problem_is_reported(self):
        write(self.bundle, "pages/0001.json", {"tampered": True})
        self.assertEqual(load(self.bundle)["integrity"], ["modified: pages/0001.json"])

    def test_reputation_legacy_unknown_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = load(full_bundle(tmp, "old", LEGACY))
            self.assertEqual(legacy["reputation"]["legacy"]["answer"], "Acme is a dentist.")
            self.assertEqual(legacy["reputation"]["legacy"]["competitors"]["rows"][0][0], "Beta")
            self.assertEqual({t["title"]: t["sub"] for t in legacy["tiles"]}["AI reputation"], "No ranking in this run")
            failed = load(full_bundle(tmp, "failed", {"status": "UNKNOWN", "reason": "llm_request_failed", "error": "no claude"}))
            self.assertEqual(failed["reputation"]["unknown"], "no claude")
            gone = full_bundle(tmp, "gone")
            (gone / "technical/llm_reputation.json").unlink()
            m = load(gone)
            self.assertEqual((m["reputation"]["state"], m["reputation"]["source"]), (MISSING, None))
            self.assertNotIn("AI reputation", [t["title"] for t in m["tiles"]])


try:
    from fastapi.testclient import TestClient
    from companyscan.web.app import create_app
except ImportError:  # The UI is an optional extra: pip install -e '.[web]'
    TestClient = None


@unittest.skipUnless(TestClient, "FastAPI not installed")
class DashboardPageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = TestClient(create_app(self.root), base_url="http://127.0.0.1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_renders_every_section_safely(self):
        full_bundle(self.root)
        page = self.client.get("/run/acme")
        self.assertEqual(page.status_code, 200)
        for anchor in ("report", "pages", "site", "meta_ads", "reputation", "social", "coverage"):
            self.assertIn(f'id="{anchor}"', page.text)
        self.assertIn("#1 of 2", page.text)
        self.assertIn("+42", page.text)
        self.assertIn('class="target"', page.text)
        self.assertIn("Not collected", page.text)  # meta_ads
        self.assertIn('class="info-card lvl-good"', page.text)
        self.assertIn('<p class="value">#1 of 2</p>', page.text)
        self.assertIn('Meta ads <small>not collected</small>', page.text)
        self.assertIn('href="/files/acme/analysis/report.md"', page.text)
        self.assertIn('href="https://acme.test/about" rel="noopener noreferrer"', page.text)
        self.assertNotIn('href="javascript:', page.text)
        self.assertIn("javascript:alert(1)", page.text)  # Shown as text.
        self.assertNotIn("<img src=x onerror", page.text)
        self.assertIn("&lt;img src=x onerror", page.text)
        self.assertIn("all artifacts verified", page.text)
        self.assertIn('class="hero-value">7<', page.text)  # One hero number: the anomaly count.
        self.assertIn('class="page-card lvl-critical"', page.text)
        self.assertIn('href="?sort=seo#pages"', page.text)
        self.assertIn('<span class="icon" aria-hidden="true">▲</span>1 serious', page.text)
        self.assertIn('<span class="icon" aria-hidden="true">!</span>6 warnings', page.text)
        self.assertIn('class="bar-row is-target"', page.text)
        self.assertIn('class="fill pos" style="left: 50%; width: 21.0%"', page.text)
        self.assertIn('href="/run/acme"', self.client.get("/").text)

    def test_wrong_shaped_json_never_500s(self):
        d = full_bundle(self.root)
        write(d, "pages/0004.json", {"id": "0004", "content_path": str((d / "content/homepage.md").resolve())})
        manifest = json.loads((d / "manifest.json").read_text())
        manifest.update(counts=1, errors=5, created_at=None, config={"dimensions": 7}, input_url="http://[")
        write(d, "manifest.json", manifest)
        write(d, "technical/measurement.json", {"tools": 3})
        write(d, "technical/aeo.json", {"issue_summary": 4})
        write(d, "technical/social-preview.json", {"issue_summary": 2})
        write(d, "technical/security.json", {"missing_summary": {"a": 1}})
        write(d, "technical/llm_reputation.json", {"scores": {"rank": 1, "leaderboard": 5, "sentiment": []}})
        page = self.client.get("/run/acme")
        self.assertEqual(page.status_code, 200)
        self.assertIn('href="/files/acme/content/homepage.md"', page.text)
        other = full_bundle(self.root, "beta")
        write(other, "manifest.json", {**json.loads((other / "manifest.json").read_text()), "counts": 1, "created_at": 7,
                                       "config": 3})
        full_bundle(self.root, "gamma")  # A normal run next to the tampered one: sorting must not mix str and int.
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_not_found(self):
        full_bundle(self.root)
        (self.root / "rep").mkdir()
        (self.root / "rep/manifest.json").write_text(json.dumps({"input_url": "acme.test"}))  # Reputation-only bundle.
        for path in ("/run/nope", "/run/..%2F..%2Fetc", "/run/rep"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_sorting_and_unreadable_files(self):
        d = full_bundle(self.root)
        write(d, "pages/0004.json", "{corrupt")
        write(d, "technical/aeo.json", "{corrupt")
        order = lambda text: [text.index(f"<h3>{t}</h3>") for t in ("Acme home", "About us", "Broken page")]
        by_path = self.client.get("/run/acme?sort=path")
        self.assertEqual(by_path.status_code, 200)
        self.assertEqual(order(by_path.text), sorted(order(by_path.text)))
        reverse = order(self.client.get("/run/acme?sort=path&desc=1").text)
        self.assertEqual(reverse, sorted(reverse, reverse=True))
        page = self.client.get("/run/acme?sort=bogus")
        self.assertEqual(page.status_code, 200)
        self.assertIn("unreadable", page.text)

if __name__ == "__main__":
    unittest.main()
