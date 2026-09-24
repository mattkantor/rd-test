import contextlib
import hashlib
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from companyscan.cli import main, parser, run
from companyscan.scan.crawler import Client, Robots, crawl, normalize
from companyscan.scan.discovery import discover
from companyscan.scan.extract import extract
from companyscan.models import Config, Response
from companyscan.scan.social import collect_profiles, discover_profiles


class Fixture(BaseHTTPRequestHandler):
    visits = []

    def do_GET(self):
        Fixture.visits.append(self.path)
        host = f"http://{self.headers['Host']}"
        routes = {
            "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /blocked\nUser-agent: GPTBot\nDisallow: /\nSitemap: " + host + "/index.xml"),
            "/sitemap.xml": (200, "application/xml", '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + host + '/about</loc></url></urlset>'),
            "/index.xml": (200, "application/xml", '<sitemapindex><sitemap><loc>' + host + '/sitemap.xml</loc></sitemap><sitemap><loc>' + host + '/index.xml</loc></sitemap></sitemapindex>'),
            "/": (200, "text/html", '''<html><head><title>Acme Dental</title><link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Lora"><style>h1 { font-family: "Brand Serif", serif }</style><meta name="description" content="Toronto family dentistry"><link rel="alternate" type="application/rss+xml" href="/feed.xml"><script type="application/ld+json">{"@type":"Dentist","name":"Acme Dental","sameAs":["https://www.linkedin.com/company/acme"]}</script></head><body><h1>Care for Toronto families</h1><p>Appointments for family dentistry.</p><a href="/about">About</a><a href="/blocked">Blocked</a><a href="/cart">Cart</a><a href="/?page=2">More</a><a href="/redirect">Redirect</a><a href="/bad-redirect">Bad redirect</a><a href="/noindex">Secret</a><a href="/broken">Broken</a><a href="https://instagram.com/acme">Instagram</a><a href="mailto:hello@acme.test">Email</a><a href="tel:+14165551234">Call us</a><img src="/team.jpg" alt="Our team"><span hidden>Hidden bait</span></body></html>'''),
            "/about": (200, "text/html", '<title>About</title><h1>Our story</h1><address>Toronto, Ontario</address><script type="application/ld+json">{broken</script><a href="/services">Services</a>'),
            "/services": (200, "text/html", '<h1>Services</h1><p>Family dental care</p>'),
            "/noindex": (200, "text/html", '<meta name="robots" content="noindex, follow"><h1>Private offering</h1>'),
            "/llms.txt": (200, "text/plain", '# Acme Dental'),
            "/style.css": (200, "text/css", '@font-face { font-family: "Acme Sans"; src: url(a.woff2) } :root { --brand: "Acme Sans", Arial } body { font-family: var(--brand), sans-serif } pre { font-family: var(--undefined) }'),
            "/broken": (503, "text/plain", 'unavailable'),
        }
        if self.path in {"/redirect", "/bad-redirect"}:
            self.send_response(301)
            self.send_header("Location", "/about" if self.path == "/redirect" else "/blocked")
            self.end_headers()
            return
        status, mime, body = routes.get(self.path, (404, "text/plain", "Not found"))
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


class ScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        Fixture.visits = []

    def command(self, args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(args)
        return code, json.loads(out.getvalue())

    def test_scan_artifacts_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, result = self.command(["scan", self.url, "--output", tmp, "--json", "--allow-private", "--delay", "0"])
            self.assertEqual(code, 1)  # Captures failure rather than aborting.
            root = Path(tmp)
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual(result["status"], "PARTIAL")
            for artifact in manifest["artifacts"]:
                self.assertEqual(hashlib.sha256((root / artifact["path"]).read_bytes()).hexdigest(), artifact["sha256"])
            pages = [json.loads(path.read_text()) for path in (root / "pages").glob("*.json")]
            home = next(p for p in pages if p["url"] == self.url + "/")
            self.assertEqual(home["title"], "Acme Dental")
            self.assertNotIn("Hidden bait", home["visible_text"])
            self.assertEqual(home["emails"], ["hello@acme.test"])
            self.assertEqual(home["telephone_numbers"], ["+14165551234"])
            self.assertTrue(home["feeds"])
            self.assertEqual(home["copy_scores"]["ai_slop"]["level"], "UNKNOWN")  # Fixture pages are under 80 words.
            self.assertIn("technical/copy-scores.json", {x["path"] for x in manifest["artifacts"]})
            self.assertEqual(json.loads((root / "technical/copy-scores.json").read_text())["pages_unscored"],
                             sum("visible_text" in p for p in pages))
            self.assertTrue(any(p.get("json_ld", {}).get("errors") for p in pages))
            self.assertNotIn("/blocked", Fixture.visits)
            self.assertNotIn("/cart", Fixture.visits)
            self.assertNotIn("/?page=2", Fixture.visits)
            social = json.loads((root / "social/discovered.json").read_text())["profiles"]
            self.assertEqual({p["network"] for p in social}, {"linkedin", "instagram"})
            self.assertTrue(all(p["status"] == "DISCOVERED_NOT_COLLECTED" for p in social))
            checks = json.loads((root / "technical/crawler-access.json").read_text())["checks"]
            self.assertTrue(all(not u["robots_allowed"] for u in checks[0]["urls"]))
            indexing = json.loads((root / "technical/indexing.json").read_text())
            self.assertTrue(next(p for p in indexing if p["url"].endswith("/noindex"))["noindex_observed"])
            for report in ("measurement", "aeo", "social-preview"):
                self.assertTrue((root / f"technical/{report}.json").exists())
            measurement = json.loads((root / "technical/measurement.json").read_text())
            self.assertFalse(measurement["has_measurement"])  # Fixture site has no analytics.
            second_code, second = self.command(["scan", self.url, "--output", tmp, "--json"])
            self.assertEqual(second_code, 2)
            self.assertEqual(second["status"], "ERROR")

    def test_dimensions_are_collected_into_hashed_bundle(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"META_ACCESS_TOKEN": ""}):
            code, result = self.command(["scan", self.url, "--output", tmp, "--json", "--allow-private", "--delay", "0",
                                         "--dimension", "security", "--dimension", "fonts", "--dimension", "meta_ads"])
            root = Path(tmp)
            manifest = json.loads((root / "manifest.json").read_text())
            hashed = {a["path"]: a["sha256"] for a in manifest["artifacts"]}
            self.assertEqual(manifest["config"]["dimensions"], ["security", "fonts", "meta_ads"])
            for name in ("security", "fonts", "meta_ads"):
                path = f"technical/{name}.json"
                self.assertEqual(hashed[path], hashlib.sha256((root / path).read_bytes()).hexdigest())
            fonts = json.loads((root / "technical/fonts.json").read_text())
            families = {f["family"] for f in fonts["families"]}
            self.assertTrue({"Acme Sans", "Arial", "Brand Serif", "Inter", "Lora", "var(--undefined)"} <= families)
            self.assertNotIn("var(--brand)", families)  # Resolved from the same stylesheet.
            sheet = next(s for s in fonts["stylesheets"] if s["url"].endswith("/style.css"))
            self.assertEqual(sheet["font_faces"], ["Acme Sans"])
            security = json.loads((root / "technical/security.json").read_text())
            home = next(p for p in security["pages"] if p["url"] == self.url + "/")
            self.assertFalse(home["https"])
            self.assertNotIn("strict-transport-security", home["missing_headers"])  # HSTS only applies over HTTPS.
            self.assertIn("content-security-policy", home["missing_headers"])
            ads = json.loads((root / "technical/meta_ads.json").read_text())
            self.assertEqual((ads["status"], ads["reason"], ads["search_terms"]), ("UNKNOWN", "no_token", "Acme Dental"))

    def test_run_reports_each_step_and_page(self):
        calls = []
        args = parser().parse_args(["scan", self.url, "--allow-private", "--delay", "0",
                                    "--dimension", "security", "--dimension", "fonts"])
        with tempfile.TemporaryDirectory() as tmp:
            result = run(args, output=Path(tmp) / "out", progress=lambda *c: calls.append(c))
        self.assertEqual(list(dict.fromkeys((c[0], c[2]) for c in calls)),
                         [(1, "Discovering sitemaps"), (2, "Crawling pages"), (3, "Running technical checks"),
                          (4, "Security headers"), (5, "Font consistency"), (6, "Writing bundle")])
        self.assertEqual({c[1] for c in calls}, {6})
        pages = [c[3:] for c in calls if c[2] == "Crawling pages" and c[3] is not None]
        self.assertEqual(pages, [(n, args.max_pages, "pages") for n in range(1, result["counts"]["pages"] + 1)])

    def test_crawl_limits(self):
        cfg = Config(max_pages=2, delay=0, allow_private=True)
        client = Client(cfg)
        discovered, robots = discover(client, self.url)
        pages, skipped = crawl(client, self.url + "/", robots, discovered["sitemap_urls"])
        self.assertEqual(len(pages), 2)
        self.assertTrue(any(item["reason"] == "page_limit" for item in skipped))
        self.assertEqual(len(discovered["sitemap"]["documents"]), 2)

    def test_depth_zero_and_commands(self):
        for command in ("discover", "crawl", "technical", "social", "accessibility"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                code, result = self.command([command, self.url, "--output", tmp, "--json", "--max-depth", "0", "--allow-private", "--delay", "0"])
                self.assertIn(code, (0, 1))
                self.assertEqual(result["counts"]["pages"], 1)
                self.assertEqual(result["accessibility"]["conformance_status"], "UNKNOWN")
                self.assertTrue((Path(tmp) / "technical/accessibility.json").is_file())
                self.assertTrue((Path(tmp) / "technical/accessibility.md").is_file())

    def test_private_target_blocked_by_default(self):
        result = Client(Config()).get(self.url)
        self.assertIn("non-public target", result.error)
        self.assertEqual(Fixture.visits, [])

    def test_unknown_and_missing_robots(self):
        for status, expected in [(503, None), (403, None), (404, True), (410, True)]:
            r = Robots(Response(self.url + "/robots.txt", self.url + "/robots.txt", status=status))
            self.assertIs(r.allowed(self.url), expected)

    def test_extraction_nested_schema_and_hidden(self):
        html = '''<head><title>Test</title><script type="application/ld+json">{"@graph":[{"@type":"Question","name":"Where?","acceptedAnswer":{"text":"Toronto"}},{"@type":"Review","reviewBody":"Great"}]}</script></head><h2>Visible <em>heading</em></h2><div style="display:none">Nope</div><p>Readable</p><link rel="canonical" href="/canonical">'''
        data = extract(html, "https://example.com/page")
        self.assertEqual(data["canonical_url"], "https://example.com/canonical")
        self.assertEqual(data["headings"][0]["text"], "Visible heading")
        self.assertNotIn("Nope", data["visible_text"])
        self.assertEqual(data["faqs"][0]["question"], "Where?")
        self.assertEqual(data["testimonials"][0]["text"], "Great")

    def test_measurement_preview_and_aeo_checks(self):
        html = '''<head><title>T</title>
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC1234567"></script>
        <script>gtag('config', 'G-ABC1234567');</script>
        <script>!function(f){}(window); fbq('init', '1234567890');</script>
        <script src="https://consent.cookiebot.com/uc.js"></script>
        <meta property="og:title" content="Acme"><meta property="og:image" content="/card.png">
        <meta name="twitter:card" content="summary_large_image">
        <script type="application/ld+json">{"@context":"https://schema.org","@graph":[
          {"@type":"LocalBusiness","@id":"#org","name":"Acme"},
          {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Hidden question?","acceptedAnswer":{"text":"Yes"}},
                                           {"@type":"Question","name":"No answer?"}]},
          {"@type":"WebPage","publisher":{"@id":"#missing"}}]}</script></head><p>No answer?</p>'''
        data = extract(html, "https://example.com/")
        tools = {t["tool"]: t for t in data["measurement"]}
        self.assertEqual(tools["Google tag (gtag.js)"]["ids"], ["G-ABC1234567"])
        gt = {t["tool"]: t for t in extract('<script src="https://www.googletagmanager.com/gtag/js?id=GT-NBBRPB6R"></script>', "https://e.com/")["measurement"]}
        self.assertEqual(gt["Google tag (gtag.js)"]["ids"], ["GT-NBBRPB6R"])
        self.assertEqual(tools["Meta Pixel"]["ids"], ["1234567890"])
        self.assertIn("Cookiebot", tools)
        self.assertNotIn("Hotjar", tools)
        self.assertEqual(data["social_meta"]["twitter:card"], "summary_large_image")
        codes = {(i["code"], i.get("property")) for i in data["json_ld"]["issues"]}
        self.assertIn(("missing_required", "address"), codes)
        self.assertIn(("incomplete_question", None), codes)
        self.assertIn(("faq_not_visible", None), codes)
        self.assertIn(("unresolved_reference", None), codes)
        stub = extract('<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"H","image":"i","datePublished":"d","author":"a","citation":{"@type":"Article","name":"Cited","url":"u"}}</script>', "https://e.com/")
        self.assertEqual(stub["json_ld"]["issues"], [])
        from companyscan.scan.technical import social_preview
        preview = social_preview([{"url": "https://example.com/", **data}])["pages"][0]["issues"]
        self.assertIn(("image_not_absolute_https", "og:image"), {(i["code"], i["tag"]) for i in preview})
        self.assertIn(("missing", "og:description"), {(i["code"], i["tag"]) for i in preview})

    def test_normalization_and_social_spoof(self):
        self.assertEqual(normalize("HTTPS://Example.COM:443/a?utm_source=x&b=2#a"), "https://example.com/a?b=2")
        profiles = discover_profiles([{"url": "https://example.com", "links": [
            {"url": "https://linkedin.com.evil.test/company/fake"}, {"url": "https://x.com/intent/tweet?text=hi"}]}])
        self.assertEqual(profiles, [])
        with self.assertRaises(ValueError):
            normalize("https://user:secret@example.com")

    def test_batch_continues_past_bad_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv = Path(tmp) / "input.csv"
            csv.write_text(f"company,domain\nAcme,{self.url}\nMissing,\n")
            code, result = self.command(["batch", str(csv), "--output", str(Path(tmp) / "out"), "--json", "--allow-private", "--delay", "0", "--max-pages", "1"])
            self.assertEqual(code, 1)
            self.assertEqual(len(result["rows"]), 2)
            self.assertEqual(result["rows"][1]["status"], "ERROR")
            self.assertTrue(Path(result["batch"]).exists())

    def test_byte_limit(self):
        response = Client(Config(allow_private=True, delay=0, max_bytes=20)).get(self.url)
        self.assertTrue(response.truncated)
        self.assertLessEqual(len(response.body), 20)

    def test_json_argument_errors_and_invalid_limits(self):
        for argv in (["scan", "example.com", "--max-pages", "0", "--json"],
                     ["scan", "example.com", "--unknown", "--json"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
                main(argv)
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(json.loads(out.getvalue())["status"], "ERROR")
        code, result = self.command(["scan", "example.com", "--delay", "nan", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "ERROR")

    def test_social_failure_and_interstitial_are_not_company_facts(self):
        url = "https://linkedin.com/company/acme"
        client = Client(Config(delay=0))
        robots = Response("https://linkedin.com/robots.txt", "https://linkedin.com/robots.txt", status=404)
        failed = Response(url, url, status=403, error="HTTP 403")
        with patch.object(client, "get", side_effect=[robots, failed]):
            profiles = collect_profiles(client, discover_profiles([], [url]))
        self.assertEqual(profiles[0]["status"], "DISCOVERED_NOT_COLLECTED")
        self.assertEqual(profiles[0]["retrieval"]["status"], 403)
        login = Response(url, url, status=200, headers={"content-type": "text/html"}, body="<title>Sign in</title><h1>Log in</h1>")
        with patch.object(client, "get", side_effect=[robots, login]):
            profiles = collect_profiles(client, discover_profiles([], [url]))
        self.assertEqual(profiles[0]["status"], "PUBLIC_HTML_CAPTURED_UNVERIFIED")
        self.assertIsNone(profiles[0]["profile"]["name"])
        self.assertEqual(profiles[0]["recent_content"], [])

    def test_external_redirect_is_recorded_without_fetch(self):
        from companyscan.scan.crawler import Redirects
        from urllib.request import Request
        client = Client(Config(allow_private=True))
        chain = []
        handler = Redirects(client, chain, self.url)
        with self.assertRaisesRegex(ValueError, "outside crawl origin"):
            handler.redirect_request(Request(self.url), None, 302, "Found", {}, "https://elsewhere.test/")
        self.assertEqual(chain[0]["to"], "https://elsewhere.test/")

    def test_canonical_aliases_do_not_expand_crawl(self):
        client = Client(Config(delay=0, allow_private=True))
        robots = Robots(Response(self.url + "/robots.txt", self.url + "/robots.txt", status=404))
        home = Response(self.url + "/", self.url + "/", status=200, headers={"content-type": "text/html"},
                        body='<link rel="canonical" href="/canonical"><h1>Home</h1><a href="/canonical">Same</a>')
        with patch.object(client, "get", return_value=home) as get:
            pages, skipped = crawl(client, self.url + "/", robots, [])
        self.assertEqual(len(pages), 1)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(skipped[0]["reason"], "duplicate_canonical")


if __name__ == "__main__":
    unittest.main()
