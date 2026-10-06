"""Customer portal: sign-in, welcome page, navigation and per-customer site ownership."""
from test_web import DJANGO, WebCase, bundle

if DJANGO:
    from django.contrib.auth.models import User
    from django.db.models import ProtectedError
    from companyscan.web.models import Site, sync


class PortalTests(WebCase):
    def setUp(self):
        super().setUp()
        self.client.logout()
        self.ann = User.objects.create_user("ann", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        bundle(self.root, "other", "https://other.test/", "2026-01-01T00:00:00+00:00")
        sync()
        self.acme = Site.objects.get(origin="https://acme.test")
        self.acme.user, self.acme.business_name = self.ann, "Acme Co"
        self.acme.save()
        self.other = Site.objects.get(origin="https://other.test")
        self.other.user = self.bob
        self.other.save()

    def test_login_is_required_and_password_sign_in_lands_on_hello_world(self):
        for url in ("/portal/content", "/portal/settings", f"/site/{self.acme.pk}", "/run/acme"):
            self.assertIn("/login", self.client.get(url)["location"], url)
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertRedirects(self.client.post("/login", {"username": "ann", "password": "pw"}), "/", fetch_redirect_response=False)
        self.assertContains(self.client.get("/"), "Welcome, ann")

    def test_navigation_lists_every_tool_with_settings_and_help_last(self):
        self.client.force_login(self.ann)
        html = self.client.get("/").content.decode()
        labels = ["Content", "Social", "Website health", "Google SEO", "Local business", "AI visibility", "Competitors", "Settings", "Help"]
        spots = [html.index(f">{label}</a>") for label in labels]
        self.assertEqual(spots, sorted(spots))
        self.assertContains(self.client.get("/portal/social"), "Coming soon")
        self.assertRedirects(self.client.get("/portal/health"), f"/site/{self.acme.pk}", fetch_redirect_response=False)

    def test_customer_sees_only_their_own_site(self):
        self.client.force_login(self.ann)
        self.assertEqual(self.client.get(f"/site/{self.acme.pk}").status_code, 200)
        self.assertEqual(self.client.get("/run/acme").status_code, 200)
        self.assertEqual(self.client.get("/files/acme/manifest.json").status_code, 200)
        for url in (f"/site/{self.other.pk}", "/run/other", "/run/other/job", "/run/other/fixpack.zip", "/files/other/manifest.json"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertNotContains(self.client.get("/portal/settings"), "other.test")
        self.assertContains(self.client.get("/portal/settings"), "Acme Co")

    def test_customer_cannot_start_jobs_or_see_staff_controls(self):
        self.client.force_login(self.ann)
        self.assertNotContains(self.client.get("/run/acme"), "Re-crawl + report")
        self.assertEqual(self.client.post("/recrawl", {"dir": "acme"})["location"].split("?")[0], "/admin/login/")

    def test_staff_keep_the_staff_pages_and_an_owner_cannot_be_deleted(self):
        self.client.force_login(User.objects.get(username="staff"))
        self.assertContains(self.client.get("/"), "acme.test")
        self.assertEqual(self.client.get("/run/other").status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        with self.assertRaises(ProtectedError):
            self.ann.delete()  # PROTECT: an owner with sites can't be deleted out from under them.
