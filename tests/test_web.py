"""Django UI tests. They run under `python manage.py test` (needs the web extra); plain unittest skips them."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from django.apps import apps
    DJANGO = apps.ready
except ImportError:  # The UI is an optional extra: pip install -e '.[web]'
    DJANGO = False

if DJANGO:
    from django.contrib.auth.models import User
    from django.db import IntegrityError, transaction
    from django.test import TestCase, override_settings
    from huey.contrib.djhuey import HUEY
    from companyscan.cli import parser
    from companyscan.dimensions import DIMENSIONS
    from companyscan.web import tasks
    from companyscan.web.models import Job, Run, Site, sync
else:
    TestCase = unittest.TestCase


def bundle(root, name, url, created):
    d = Path(root) / name
    (d / "analysis").mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"input_url": url, "created_at": created, "status": "COMPLETE",
                                                 "counts": {"pages": 3}, "config": {"dimensions": ["security"]}}))
    return d


@unittest.skipUnless(DJANGO, "run with python manage.py test")
class WebCase(TestCase):
    """Staff user logged in, an empty output root, and Huey running tasks inline."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.settings = override_settings(COMPANYSCAN_OUTPUT=self.root)
        self.settings.enable()
        HUEY.immediate = True
        self.client.force_login(User.objects.create_user("staff", is_staff=True))

    def tearDown(self):
        self.settings.disable()
        self.tmp.cleanup()

    def job(self, site="https://acme.test"):
        return Job.objects.filter(site__origin=site).first()


class WebTests(WebCase):
    def test_latest_crawl_per_site_is_last_crawled(self):
        bundle(self.root, "acme-old", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        new = bundle(self.root, "acme-new", "https://acme.test/about", "2026-02-01T00:00:00+00:00")
        (new / "analysis/report.md").write_text("# Acme")
        bundle(self.root, "beta", "https://beta.test/", "2026-01-15T00:00:00+00:00")
        (self.root / "rep").mkdir()  # Reputation-only bundle: no crawl counts.
        (self.root / "rep/manifest.json").write_text(json.dumps({"input_url": "acme.test", "created_at": "2026-03-01"}))
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(sorted(Run.objects.values_list("name", flat=True)), ["acme-new", "acme-old", "beta"])
        self.assertEqual(Site.objects.get(origin="https://acme.test").runs.first().name, "acme-new")
        text = page.content.decode()
        self.assertLess(text.index("acme.test"), text.index("beta.test"))
        self.assertIn("2 crawl(s)", text)
        self.assertIn('href="/files/acme-new/analysis/report.md"', text)
        self.assertIn("/static/app.css", text)
        response = self.client.get("/files/acme-new/analysis/report.md")
        self.assertEqual(b"".join(response.streaming_content), b"# Acme")
        self.assertIn("text/plain", response["content-type"])
        (self.root / "beta/manifest.json").unlink()
        sync()
        self.assertFalse(Run.objects.filter(name="beta").exists())  # The disk is the record.

    def test_crawl_runs_job_and_records_status(self):
        seen = {}

        def fake_run(args, output, progress=None):
            seen.update(url=args.target, dimensions=args.dimensions, output=output)
            progress(2, 4, "Crawling pages", 3, 50, "pages")
            seen["mid"] = self.job()
            return {"counts": {"pages": 7}, "status": "COMPLETE"}

        with patch.object(tasks, "run", fake_run):
            response = self.client.post("/crawl", {"url": "acme.test", "dimension": ["fonts", "bogus"]})
        self.assertEqual((response.status_code, response["location"]), (302, "/"))
        self.assertEqual((seen["url"], seen["dimensions"]), ("https://acme.test/", ["fonts"]))
        self.assertEqual(seen["output"].parent, self.root)
        mid = seen["mid"]
        self.assertEqual((mid.state, mid.label, mid.kind, mid.step, mid.steps),
                         ("running", "Crawling pages: 3 of 50 pages", "crawl", 2, 4))
        job = self.job()
        self.assertEqual((job.state, job.label, job.run), ("done", "Crawled 7 pages (COMPLETE)", seen["output"].name))
        self.assertTrue(job.finished)

    def test_bad_url_busy_site_and_unknown_bundle(self):
        response = self.client.post("/crawl", {"url": "ftp://acme.test"})
        self.assertIn("msg=", response["location"])
        site = Site.objects.create(origin="https://acme.test")
        Job.objects.create(site=site, kind="crawl", run="x")
        with patch.object(tasks, "run") as run:
            response = self.client.post("/crawl", {"url": "https://acme.test"})
        self.assertIn("already+has+a+job", response["location"])
        run.assert_not_called()
        response = self.client.post("/report", {"dir": "../../etc"})
        self.assertIn("Unknown+crawl", response["location"])

    def test_one_running_job_per_site_is_a_db_constraint(self):
        site = Site.objects.create(origin="https://acme.test")
        Job.objects.create(site=site, kind="crawl", run="a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Job.objects.create(site=site, kind="report", run="b")
        Job.objects.update(state="done")
        Job.objects.create(site=site, kind="report", run="b")  # Finished jobs don't block.

    def test_site_details_become_scan_flags(self):
        site = Site(origin="https://joes.test", business_name="Joe's", icp="-takeout families", city="Austin", state="TX")
        args = parser().parse_args(["scan", site.origin, *site.scan_args()])
        self.assertEqual((args.company_name, args.icp, args.location), ("Joe's", "-takeout families", "Austin, TX"))
        self.assertEqual(Site(origin="https://x.test").scan_args(), [])

    def test_report_job_runs_analysis_then_pdf(self):
        d = bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        calls = []
        with patch.object(tasks, "analyze", lambda b: calls.append(("analyze", b))), \
                patch.object(tasks, "render_pdf", lambda b: calls.append(("pdf", b))):
            self.client.post("/report", {"dir": "acme"})
        self.assertEqual(calls, [("analyze", d), ("pdf", d)])
        self.assertEqual(self.job().state, "done")

    def test_job_errors_are_shown_not_lost(self):
        with patch.object(tasks, "run", side_effect=ValueError("disk full")):
            self.client.post("/crawl", {"url": "https://acme.test"})
        self.assertEqual((self.job().state, self.job().label), ("error", "disk full"))

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
            seen["mid"] = self.job()

        with patch.object(tasks, "run", fake_run), patch.object(tasks, "analyze", fake_analyze), \
                patch.object(tasks, "render_pdf", lambda b: reports.append(("pdf", b))):
            response = self.client.post("/recrawl", {"dir": "acme"})
        self.assertEqual((response.status_code, response["location"]), (302, "/"))
        self.assertEqual((seen["url"], seen["dimensions"]), ("https://acme.test/about", list(DIMENSIONS)))
        self.assertEqual(reports, [("analyze", seen["output"]), ("pdf", seen["output"])])  # The report is for the new run.
        self.assertEqual((seen["mid"].step, seen["mid"].steps), (7, 8))  # 6 crawl steps + analysis + PDF.
        self.assertEqual(seen["output"].parent, self.root)  # A new timestamped run; the old bundle is untouched.
        self.assertTrue((self.root / "acme/manifest.json").is_file())
        job = self.job()
        self.assertEqual((job.state, job.label, job.kind), ("done", "Crawled 2 pages (COMPLETE) · report ready", "recrawl"))

    def test_recrawl_report_failure_keeps_the_crawl_result(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        with patch.object(tasks, "run", lambda args, output, progress=None: {"counts": {"pages": 2}, "status": "PARTIAL"}), \
                patch.object(tasks, "analyze", side_effect=ValueError("claude not logged in")), \
                patch.object(tasks, "render_pdf") as pdf:
            self.client.post("/recrawl", {"dir": "acme"})
        job = self.job()
        self.assertEqual((job.state, job.label), ("error", "Crawled 2 pages (PARTIAL), but the report failed: claude not logged in"))
        pdf.assert_not_called()

    def test_recrawl_refuses_unknown_non_crawl_and_busy(self):
        (self.root / "rep").mkdir()
        (self.root / "rep/manifest.json").write_text(json.dumps({"input_url": "https://acme.test/"}))  # No counts.
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        Job.objects.create(site=Site.objects.create(origin="https://acme.test"), kind="crawl", run="x")
        with patch.object(tasks, "run") as run:
            for name in ("../../etc", "nope", "rep"):
                response = self.client.post("/recrawl", {"dir": name})
                self.assertIn("Unknown+crawl", response["location"], name)
            response = self.client.post("/recrawl", {"dir": "acme"})
            self.assertIn("already+has+a+job", response["location"])
        run.assert_not_called()

    def test_site_page_shows_latest_run_and_history(self):
        bundle(self.root, "acme-old", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        bundle(self.root, "acme-new", "https://acme.test/", "2026-02-01T00:00:00+00:00")
        home = self.client.get("/")
        pk = Site.objects.get(origin="https://acme.test").pk
        self.assertContains(home, f'href="/site/{pk}"')
        page = self.client.get(f"/site/{pk}")
        self.assertContains(page, 'name="dir" value="acme-new"')
        self.assertContains(page, "History · 2 assessments")
        self.assertContains(page, 'href="/run/acme-old"')
        self.assertContains(page, 'name="return_to" value="site"')
        old = self.client.get("/run/acme-old")
        self.assertContains(old, "older assessment")
        self.assertContains(old, f'href="/site/{pk}">Current assessment')
        with patch.object(tasks, "analyze", lambda b: None), patch.object(tasks, "render_pdf", lambda b: None):
            self.assertEqual(self.client.post("/report", {"dir": "acme-old", "return_to": "site"})["location"], f"/site/{pk}")
        self.assertEqual(self.client.get("/site/999").status_code, 404)

    def test_edit_site_profile_but_not_its_url(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        self.client.get("/")
        site = Site.objects.get()
        self.assertContains(self.client.get(f"/site/{site.pk}"), f'href="/site/{site.pk}/edit">Edit profile')
        page = self.client.get(f"/site/{site.pk}/edit")
        self.assertContains(page, 'value="https://acme.test" disabled')
        self.assertNotContains(page, 'name="origin"')
        response = self.client.post(f"/site/{site.pk}/edit", {"origin": "https://evil.test", "business_name": "Acme Dental",
                                                               "icp": "families", "city": "Austin", "state": "TX", "country": ""})
        self.assertEqual(response["location"], f"/site/{site.pk}")
        site.refresh_from_db()
        self.assertEqual((site.origin, site.business_name, site.location), ("https://acme.test", "Acme Dental", "Austin, TX"))
        self.assertContains(self.client.get(f"/site/{site.pk}"), "<strong>Acme Dental</strong>")
        self.assertEqual(self.client.get("/site/999/edit").status_code, 404)
        self.client.force_login(User.objects.create_superuser("admin"))
        self.assertNotContains(self.client.get(f"/admin/web/site/{site.pk}/change/"), 'name="origin"')
        self.assertContains(self.client.get("/admin/web/site/add/"), 'name="origin"')

    def test_recrawl_buttons_on_home_and_dashboard(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        for path in ("/", "/run/acme"):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200, path)
            self.assertContains(page, 'action="/recrawl"')
            self.assertContains(page, 'name="dir" value="acme"')
            self.assertContains(page, 'name="csrfmiddlewaretoken"')

    def test_percent(self):
        percent = lambda **kw: Job(**{"state": "running", **kw}).percent
        self.assertEqual(percent(step=2, steps=4, done=25, total=50), 37)
        self.assertEqual(percent(step=3, steps=4), 50)
        self.assertEqual(percent(step=0, steps=0), 0)
        self.assertEqual(percent(step=1, steps=2, done=9, total=3), 50)  # Clamped.
        self.assertEqual(percent(state="done"), 100)

    def test_dashboard_shows_job_status(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        self.assertNotContains(self.client.get("/run/acme"), 'class="job')
        job = Job.objects.create(site=Site.objects.get_or_create(origin="https://acme.test")[0], kind="recrawl", run="acme-new",
                                 label="Re-crawling with every check…")
        self.assertContains(self.client.get("/run/acme"), "starting…")
        Job.objects.filter(pk=job.pk).update(step=2, steps=4, done=25, total=50, label="Crawling pages: 25 of 50 pages")
        page = self.client.get("/run/acme")
        for text in ('data-poll="/run/acme/job"', "Re-crawl running · step 2 of 4", "width: 37%", "Crawling pages: 25 of 50 pages",
                     "<button data-busy disabled>Re-crawl + report"):
            self.assertContains(page, text)
        self.assertNotContains(page, 'http-equiv="refresh"')  # Only the panel is polled, not the page.
        panel = self.client.get("/run/acme/job")  # What the dashboard polls: the panel alone.
        self.assertContains(panel, "width: 37%")
        self.assertContains(panel, "job-running")
        self.assertNotContains(panel, "<html")
        self.assertEqual(self.client.get("/run/nope/job").status_code, 404)
        Job.objects.filter(pk=job.pk).update(state="done", label="Crawled 50 pages (PARTIAL)")
        self.assertNotContains(self.client.get("/run/acme/job"), "job-running")
        page = self.client.get("/run/acme")
        self.assertContains(page, 'href="/run/acme-new">View new run')
        Job.objects.filter(pk=job.pk).update(state="error", label="disk full")
        self.assertContains(self.client.get("/run/acme"), "Re-crawl failed: disk full")

    def test_home_polls_a_small_status_per_running_job(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        self.client.get("/")
        acme = Site.objects.get()
        new = Site.objects.create(origin="https://new.test")  # First crawl: no run, so no table row yet.
        Job.objects.create(site=acme, kind="recrawl", run="acme-2", step=2, steps=4, label="Crawling pages")
        Job.objects.create(site=new, kind="crawl", run="new-1", label="Crawling…")
        page = self.client.get("/")
        self.assertNotContains(page, 'http-equiv="refresh"')
        for text in (f'data-poll="/site/{acme.pk}/job"', f'data-poll="/site/{new.pk}/job"', 'class="pending"',
                     "<button data-busy disabled>Re-crawl + report", "/static/poll.js", "width: 25%"):
            self.assertContains(page, text)
        mini = self.client.get(f"/site/{acme.pk}/job")
        self.assertContains(mini, "job-running")
        self.assertContains(mini, "Crawling pages · 25%")
        self.assertNotContains(mini, "<html")
        Job.objects.filter(site=acme).update(state="done", label="Crawled 3 pages (COMPLETE)")
        self.assertNotContains(self.client.get(f"/site/{acme.pk}/job"), "job-running")
        self.assertEqual(self.client.get("/site/999/job").status_code, 404)

    def test_dashboard_buttons_return_to_the_dashboard(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        with patch.object(tasks, "run", lambda args, output, progress=None: {"counts": {"pages": 1}, "status": "COMPLETE"}), \
                patch.object(tasks, "analyze", lambda b: None), patch.object(tasks, "render_pdf", lambda b: None):
            response = self.client.post("/recrawl", {"dir": "acme", "return_to": "dashboard"})
            self.assertEqual(response["location"], "/run/acme")
            response = self.client.post("/report", {"dir": "acme", "return_to": "dashboard"})
            self.assertEqual(response["location"], "/run/acme")
            response = self.client.post("/report", {"dir": "acme", "return_to": "https://evil.test"})
            self.assertEqual(response["location"], "/")
        self.assertContains(self.client.get("/run/acme"), 'name="return_to" value="dashboard"')

    def test_admin_lists_runs_with_dashboard_link_and_starts_jobs(self):
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        self.client.force_login(User.objects.create_superuser("admin"))
        page = self.client.get("/admin/web/run/")
        self.assertContains(page, 'href="/run/acme"')
        with patch.object(tasks, "analyze", lambda b: None), patch.object(tasks, "render_pdf", lambda b: None):
            self.client.post("/admin/web/run/", {"action": "generate_report", "_selected_action": [Run.objects.get().pk]})
        self.assertEqual((self.job().kind, self.job().state), ("report", "done"))

    def test_staff_login_hosts_and_csrf_are_enforced(self):
        self.client.logout()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["location"])
        self.assertEqual(self.client.get("/files/anything").status_code, 302)
        self.client.force_login(User.objects.create_user("plain"))  # Logged in but not staff.
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/", HTTP_HOST="evil.test").status_code, 400)  # DNS rebinding.
        self.client.force_login(User.objects.get(username="staff"))
        self.client.handler.enforce_csrf_checks = True
        self.assertEqual(self.client.post("/crawl", {"url": "https://acme.test"}).status_code, 403)
        self.assertFalse(Job.objects.exists())
        self.assertEqual(self.client.get("/files/../../etc/passwd").status_code, 404)
        self.assertEqual(self.client.get("/crawl").status_code, 405)


if __name__ == "__main__":
    unittest.main()
