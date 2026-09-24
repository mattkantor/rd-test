import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    from companyscan.web import jobs
    from companyscan.web.app import create_app, sites
    from companyscan.dimensions import DIMENSIONS
except ImportError:  # The UI is an optional extra: pip install -e '.[web]'
    TestClient = None


def bundle(root, name, url, created):
    d = Path(root) / name
    (d / "analysis").mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"input_url": url, "created_at": created, "status": "COMPLETE",
                                                 "counts": {"pages": 3}, "config": {"dimensions": ["security"]}}))
    return d


@unittest.skipUnless(TestClient, "FastAPI not installed")
class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = TestClient(create_app(self.root), base_url="http://127.0.0.1")
        jobs.JOBS.clear()

    def tearDown(self):
        self.tmp.cleanup()
        jobs.JOBS.clear()

    def test_latest_crawl_per_site_is_last_crawled(self):
        bundle(self.root, "acme-old", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        new = bundle(self.root, "acme-new", "https://acme.test/about", "2026-02-01T00:00:00+00:00")
        (new / "analysis/report.md").write_text("# Acme")
        bundle(self.root, "beta", "https://beta.test/", "2026-01-15T00:00:00+00:00")
        (self.root / "rep").mkdir()  # Reputation-only bundle: no crawl counts.
        (self.root / "rep/manifest.json").write_text(json.dumps({"input_url": "acme.test", "created_at": "2026-03-01"}))
        result = sites(self.root)
        self.assertEqual([g["site"] for g in result], ["https://acme.test", "https://beta.test"])
        self.assertEqual((result[0]["runs"], result[0]["latest"]["dir"].name), (2, "acme-new"))
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("acme.test", page.text)
        self.assertIn('href="/files/acme-new/analysis/report.md"', page.text)
        self.assertIn("/static/app.css", page.text)
        self.assertEqual(self.client.get("/files/acme-new/analysis/report.md").text, "# Acme")
        self.assertIn("text/plain", self.client.get("/files/acme-new/analysis/report.md").headers["content-type"])

    def test_crawl_runs_job_and_records_status(self):
        seen = {}

        def fake_run(args, output, progress=None):
            seen.update(url=args.target, dimensions=args.dimensions, output=output)
            progress(2, 4, "Crawling pages", 3, 50, "pages")
            seen["mid"] = dict(jobs.JOBS["https://acme.test"])
            return {"counts": {"pages": 7}, "status": "COMPLETE"}

        with patch.object(jobs, "run", fake_run):
            response = self.client.post("/crawl", data={"url": "acme.test", "dimension": ["fonts", "bogus"]}, follow_redirects=False)
        self.assertEqual((response.status_code, response.headers["location"]), (303, "/"))
        self.assertEqual((seen["url"], seen["dimensions"]), ("https://acme.test/", ["fonts"]))
        self.assertEqual(seen["output"].parent, self.root)
        self.assertEqual({k: seen["mid"][k] for k in ("state", "label", "kind", "step", "steps")},
                         {"state": "running", "label": "Crawling pages: 3 of 50 pages", "kind": "crawl", "step": 2, "steps": 4})
        job = jobs.JOBS["https://acme.test"]
        self.assertEqual((job["state"], job["label"], job["run"]), ("done", "Crawled 7 pages (COMPLETE)", seen["output"].name))
        self.assertTrue(job["finished"])

    def test_bad_url_busy_site_and_unknown_bundle(self):
        response = self.client.post("/crawl", data={"url": "ftp://acme.test"}, follow_redirects=False)
        self.assertIn("msg=", response.headers["location"])
        jobs.claim("https://acme.test", "Crawling…")
        response = self.client.post("/crawl", data={"url": "https://acme.test"}, follow_redirects=False)
        self.assertIn("already+has+a+job", response.headers["location"])
        response = self.client.post("/report", data={"dir": "../../etc"}, follow_redirects=False)
        self.assertIn("Unknown+crawl", response.headers["location"])

    def test_report_job_runs_analysis_then_pdf(self):
        d = bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        calls = []
        with patch.object(jobs, "analyze", lambda b: calls.append(("analyze", b))), \
                patch.object(jobs, "render_pdf", lambda b: calls.append(("pdf", b))):
            self.client.post("/report", data={"dir": "acme"}, follow_redirects=False)
        self.assertEqual(calls, [("analyze", d.resolve()), ("pdf", d.resolve())])
        self.assertEqual(jobs.JOBS["https://acme.test"]["state"], "done")

    def test_job_errors_are_shown_not_lost(self):
        with patch.object(jobs, "run", side_effect=ValueError("disk full")):
            self.client.post("/crawl", data={"url": "https://acme.test"})
        self.assertEqual({k: jobs.JOBS["https://acme.test"][k] for k in ("state", "label")}, {"state": "error", "label": "disk full"})

    def test_recrawl_runs_every_check_on_the_bundle_url(self):
        bundle(self.root, "acme", "https://acme.test/about", "2026-01-01T00:00:00+00:00")
        seen = {}

        def fake_run(args, output, progress=None):
            seen.update(url=args.target, dimensions=args.dimensions, output=output)
            progress(6, 6, "Writing bundle")
            return {"counts": {"pages": 2}, "status": "COMPLETE"}

        reports = []

        def fake_analyze(bundle):
            reports.append(("analyze", bundle))
            seen["mid"] = dict(jobs.JOBS["https://acme.test"])

        with patch.object(jobs, "run", fake_run), patch.object(jobs, "analyze", fake_analyze), \
                patch.object(jobs, "render_pdf", lambda b: reports.append(("pdf", b))):
            response = self.client.post("/recrawl", data={"dir": "acme"}, follow_redirects=False)
        self.assertEqual((response.status_code, response.headers["location"]), (303, "/"))
        self.assertEqual((seen["url"], seen["dimensions"]), ("https://acme.test/about", list(DIMENSIONS)))
        self.assertEqual(reports, [("analyze", seen["output"]), ("pdf", seen["output"])])  # The report is for the new run.
        self.assertEqual((seen["mid"]["step"], seen["mid"]["steps"]), (7, 8))  # 6 crawl steps + analysis + PDF.
        self.assertEqual(seen["output"].parent, self.root)  # A new timestamped run; the old bundle is untouched.
        self.assertTrue((self.root / "acme/manifest.json").is_file())
        job = jobs.JOBS["https://acme.test"]
        self.assertEqual((job["state"], job["label"], job["kind"]), ("done", "Crawled 2 pages (COMPLETE) · report ready", "recrawl"))

    def test_recrawl_report_failure_keeps_the_crawl_result(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        with patch.object(jobs, "run", lambda args, output, progress=None: {"counts": {"pages": 2}, "status": "PARTIAL"}), \
                patch.object(jobs, "analyze", side_effect=ValueError("claude not logged in")), patch.object(jobs, "render_pdf") as pdf:
            self.client.post("/recrawl", data={"dir": "acme"})
        job = jobs.JOBS["https://acme.test"]
        self.assertEqual((job["state"], job["label"]), ("error", "Crawled 2 pages (PARTIAL), but the report failed: claude not logged in"))
        pdf.assert_not_called()

    def test_recrawl_refuses_unknown_non_crawl_and_busy(self):
        (self.root / "rep").mkdir()
        (self.root / "rep/manifest.json").write_text(json.dumps({"input_url": "https://acme.test/"}))  # No counts.
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        jobs.claim("https://acme.test", "Crawling…")
        with patch.object(jobs, "run") as run:
            for name in ("../../etc", "nope", "rep"):
                response = self.client.post("/recrawl", data={"dir": name}, follow_redirects=False)
                self.assertIn("Unknown+crawl", response.headers["location"], name)
            response = self.client.post("/recrawl", data={"dir": "acme"}, follow_redirects=False)
            self.assertIn("already+has+a+job", response.headers["location"])
        run.assert_not_called()

    def test_recrawl_buttons_on_home_and_dashboard(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        for path in ("/", "/run/acme"):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200, path)
            self.assertIn('action="/recrawl"', page.text, path)
            self.assertIn('name="dir" value="acme"', page.text, path)

    def test_percent(self):
        self.assertEqual(jobs.percent({"state": "running", "step": 2, "steps": 4, "done": 25, "total": 50}), 37)
        self.assertEqual(jobs.percent({"state": "running", "step": 3, "steps": 4, "done": None, "total": None}), 50)
        self.assertEqual(jobs.percent({"state": "running", "step": 0, "steps": 0}), 0)
        self.assertEqual(jobs.percent({"state": "running", "step": 1, "steps": 2, "done": 9, "total": 3}), 50)  # Clamped.
        self.assertEqual(jobs.percent({"state": "done"}), 100)

    def test_dashboard_shows_job_status(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        self.assertNotIn('class="job', self.client.get("/run/acme").text)
        jobs.claim("https://acme.test", "Re-crawling with every check…", "recrawl", "acme-new")
        self.assertIn("starting…", self.client.get("/run/acme").text)
        jobs.JOBS["https://acme.test"].update(step=2, steps=4, done=25, total=50, label="Crawling pages: 25 of 50 pages")
        page = self.client.get("/run/acme").text
        for text in ('http-equiv="refresh"', "Re-crawl running · step 2 of 4", "width: 37%", "Crawling pages: 25 of 50 pages",
                     "<button disabled>Re-crawl + report"):
            self.assertIn(text, page)
        jobs.JOBS["https://acme.test"].update(state="done", label="Crawled 50 pages (PARTIAL)", finished=jobs.now())
        page = self.client.get("/run/acme").text
        self.assertNotIn('http-equiv="refresh"', page)
        self.assertIn('href="/run/acme-new">View new run', page)
        jobs.JOBS["https://acme.test"].update(state="error", label="disk full")
        self.assertIn("Re-crawl failed: disk full", self.client.get("/run/acme").text)

    def test_dashboard_buttons_return_to_the_dashboard(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        with patch.object(jobs, "run", lambda args, output, progress=None: {"counts": {"pages": 1}, "status": "COMPLETE"}), \
                patch.object(jobs, "analyze", lambda b: None), patch.object(jobs, "render_pdf", lambda b: None):
            response = self.client.post("/recrawl", data={"dir": "acme", "return_to": "dashboard"}, follow_redirects=False)
        self.assertEqual(response.headers["location"], "/run/acme")
        with patch.object(jobs, "analyze", lambda b: None), patch.object(jobs, "render_pdf", lambda b: None):
            response = self.client.post("/report", data={"dir": "acme", "return_to": "dashboard"}, follow_redirects=False)
            self.assertEqual(response.headers["location"], "/run/acme")
            response = self.client.post("/report", data={"dir": "acme", "return_to": "https://evil.test"}, follow_redirects=False)
            self.assertEqual(response.headers["location"], "/")
        self.assertIn('name="return_to" value="dashboard"', self.client.get("/run/acme").text)

    def test_only_localhost_hosts_and_origins_are_served(self):
        self.assertEqual(TestClient(create_app(self.root), base_url="http://evil.test").get("/").status_code, 400)  # DNS rebinding.
        response = self.client.post("/crawl", data={"url": "https://acme.test"}, headers={"Origin": "https://evil.test"})
        self.assertEqual(response.status_code, 403)  # CSRF.
        self.assertNotIn("https://acme.test", jobs.JOBS)
        self.assertEqual(self.client.get("/files/../../etc/passwd").status_code, 404)
        self.assertEqual(self.client.get("/docs").status_code, 404)


if __name__ == "__main__":
    unittest.main()
