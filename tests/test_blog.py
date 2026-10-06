"""Scheduled blog drafts: profile fields, keyword rotation, the generator call, the schedule and customer approval."""
import unittest
from datetime import timedelta
from unittest.mock import patch

from test_report import StubReport
from test_web import DJANGO, WebCase, bundle

from companyscan import blog

if DJANGO:
    from django.contrib.auth.models import User
    from django.utils import timezone
    from companyscan.web import tasks
    from companyscan.web.models import BlogPost, Job, Site, sync

POST = {"title": "Why sourdough", "meta_description": "m" * 200, "body": "## Hello"}


class KeywordTests(unittest.TestCase):
    def test_skips_recent_keywords_and_repeats_only_when_allowed(self):
        self.assertEqual(blog.next_keyword("a\nb, c", ["A", "b"]), "c")
        self.assertIsNone(blog.next_keyword("a\nb", ["b", "a"]))
        self.assertEqual(blog.next_keyword("a\nb", ["b", "a"], repeat=True), "a")  # "a" is the older use.
        self.assertIsNone(blog.next_keyword("", [], repeat=True))


class BlogTests(WebCase):
    def setUp(self):
        super().setUp()
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        (self.root / "acme/pages").mkdir()
        (self.root / "acme/pages/0001.json").write_text('{"url": "https://acme.test/", "title": "Acme bakery", "visible_text": "We bake sourdough."}')
        sync()
        self.ann = User.objects.create_user("ann")
        self.site = Site.objects.get()
        self.site.user, self.site.keywords, self.site.offering = self.ann, "sourdough\nrye", "We bake bread"
        self.site.blog_every_days = 7
        self.site.save()
        self.stub = StubReport(POST)
        patcher = patch.object(blog, "chat_model", return_value=self.stub)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_new_fields_save_from_the_staff_form_and_show_in_settings(self):
        form = {"keywords": "pies", "offering": "Pies", "blog_per_run": 2, "blog_every_days": 3}
        self.assertEqual(self.client.post(f"/site/{self.site.pk}/edit", form).status_code, 302)
        self.site.refresh_from_db()
        self.assertEqual((self.site.keywords, self.site.offering, self.site.blog_every_days), ("pies", "Pies", 3))
        self.client.force_login(self.ann)
        self.assertContains(self.client.get("/portal/settings"), "Pies")

    def test_generator_gets_the_profile_keyword_and_crawl_text(self):
        tasks.schedule_blogs()
        system, user = self.stub.messages[0][1], self.stub.messages[1][1]
        self.assertIn("only facts", system)
        for text in ("Target keyword: sourdough", "We bake bread", "We bake sourdough.", '"rye"'):
            self.assertIn(text, user)
        post = BlogPost.objects.get()
        self.assertEqual((post.status, post.keyword, post.run, post.profile["offering"]), ("draft", "sourdough", "acme", "We bake bread"))
        self.assertEqual(len(post.meta_description), 160)
        self.assertEqual(self.job().kind, "blog")

    def test_runs_on_schedule_and_never_repeats_a_keyword(self):
        tasks.schedule_blogs()
        tasks.schedule_blogs()  # Not due again yet.
        self.assertEqual(BlogPost.objects.count(), 1)
        BlogPost.objects.update(created_at=timezone.now() - timedelta(days=8))
        tasks.schedule_blogs()
        self.assertEqual(list(BlogPost.objects.order_by("id").values_list("keyword", flat=True)), ["sourdough", "rye"])
        BlogPost.objects.update(created_at=timezone.now() - timedelta(days=8))
        tasks.schedule_blogs()  # Both keywords used: nothing new is drafted, and no failing job is queued.
        self.assertEqual(BlogPost.objects.count(), 2)
        self.assertFalse(Job.objects.filter(state="error").exists())
        self.site.blog_repeat_keywords = True
        self.site.save()
        tasks.schedule_blogs()
        self.assertEqual(BlogPost.objects.order_by("id").last().keyword, "sourdough")

    def test_no_schedule_means_no_drafts(self):
        Site.objects.update(blog_every_days=None)
        tasks.schedule_blogs()
        self.assertFalse(BlogPost.objects.exists())

    def test_only_the_owner_decides_and_nothing_publishes_unapproved(self):
        tasks.schedule_blogs()
        post = BlogPost.objects.get()
        self.client.force_login(self.ann)
        self.assertContains(self.client.get("/portal/content"), "Why sourdough")
        self.assertEqual(post.status, "draft")
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.post(f"/portal/content/{post.pk}/approve").status_code, 404)
        self.assertNotContains(self.client.get("/portal/content"), "Why sourdough")
        self.client.force_login(self.ann)
        self.assertEqual(self.client.get(f"/portal/content/{post.pk}/approve").status_code, 405)
        self.client.post(f"/portal/content/{post.pk}/approve")
        post.refresh_from_db()
        self.assertEqual((post.status, post.decided_by), ("approved", self.ann))
        self.client.post(f"/portal/content/{post.pk}/reject")  # Decided posts stay decided.
        post.refresh_from_db()
        self.assertEqual(post.status, "approved")
