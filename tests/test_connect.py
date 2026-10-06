"""Settings > Website connection: choose a site, store credentials encrypted, disconnect; owner only."""
import os
from unittest.mock import patch

from test_web import DJANGO, WebCase, bundle

if DJANGO:
    from cryptography.fernet import Fernet
    from django.contrib.auth.models import User
    from companyscan.google import oauth
    from companyscan.web.models import Site, SiteConnection, sync

FORM = {"platform": "wordpress", "admin_url": "https://acme.test/wp-admin", "username": "ann", "secret": "s3cret-token"}


class ConnectTests(WebCase):
    def setUp(self):
        super().setUp()
        env = patch.dict(os.environ, {"GOOGLE_TOKEN_KEY": Fernet.generate_key().decode()})
        env.start()
        self.addCleanup(env.stop)
        for name in ("acme", "other", "mine2"):
            bundle(self.root, name, f"https://{name}.test/", "2026-01-01T00:00:00+00:00")
        sync()
        self.ann, self.bob = User.objects.create_user("ann"), User.objects.create_user("bob")
        Site.objects.filter(origin__in=["https://acme.test", "https://mine2.test"]).update(user=self.ann)
        Site.objects.filter(origin="https://other.test").update(user=self.bob)
        self.acme, self.other = Site.objects.get(origin="https://acme.test"), Site.objects.get(origin="https://other.test")
        self.client.force_login(self.ann)
        self.url = f"/portal/settings/website?site={self.acme.pk}"

    def test_subpage_is_linked_from_settings_and_keeps_settings_highlighted(self):
        self.assertContains(self.client.get("/portal/settings"), 'href="/portal/settings/website"')
        self.assertIn('href="/portal/settings" aria-current="page"', self.client.get("/portal/settings/website").content.decode())

    def test_chooser_lists_only_own_sites_and_shows_the_chosen_ones_form(self):
        page = self.client.get(self.url)
        self.assertContains(page, "acme.test</option>")
        self.assertContains(page, "mine2.test</option>")
        self.assertNotContains(page, "other.test")
        self.assertContains(page, f'action="/portal/settings/website?site={self.acme.pk}"')
        self.assertContains(self.client.get("/portal/settings/website?site=%d" % self.other.pk), f'site={self.acme.pk}')  # Not theirs: falls back to their first.

    def test_saves_the_secret_encrypted_and_never_shows_it_again(self):
        self.assertEqual(self.client.post(self.url, FORM).status_code, 302)
        conn = SiteConnection.objects.get()
        self.assertEqual((conn.site, conn.platform, conn.username), (self.acme, "wordpress", "ann"))
        self.assertNotIn("s3cret", conn.secret)
        self.assertEqual(oauth.decrypt(conn.secret), "s3cret-token")
        page = self.client.get(self.url).content.decode()
        self.assertNotIn("s3cret", page)
        self.assertIn("https://acme.test/wp-admin", page)
        self.assertIn("Update connection", page)

    def test_blank_secret_keeps_the_saved_one_but_is_required_the_first_time(self):
        self.assertContains(self.client.post(self.url, {**FORM, "secret": ""}), "Enter the password or token")
        self.assertFalse(SiteConnection.objects.exists())
        self.client.post(self.url, FORM)
        before = SiteConnection.objects.get().secret
        self.client.post(self.url, {**FORM, "secret": "", "username": "ann2"})
        conn = SiteConnection.objects.get()
        self.assertEqual((conn.secret, conn.username), (before, "ann2"))

    def test_rejects_a_bad_url_and_refuses_to_store_without_an_encryption_key(self):
        self.assertContains(self.client.post(self.url, {**FORM, "admin_url": "not a url"}), "Enter a valid URL")
        with patch.dict(os.environ, {"GOOGLE_TOKEN_KEY": ""}):
            self.assertContains(self.client.post(self.url, FORM), "GOOGLE_TOKEN_KEY")
        self.assertFalse(SiteConnection.objects.exists())

    def test_disconnect_deletes_credentials_and_only_the_owner_may(self):
        self.client.post(self.url, FORM)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(f"/portal/settings/website/{self.acme.pk}/disconnect").status_code, 404)
        self.assertTrue(SiteConnection.objects.exists())
        self.client.force_login(self.ann)
        self.client.post(f"/portal/settings/website/{self.acme.pk}/disconnect")
        self.assertFalse(SiteConnection.objects.exists())

    def test_login_required(self):
        self.client.logout()
        self.assertIn("/login", self.client.get(self.url)["location"])
