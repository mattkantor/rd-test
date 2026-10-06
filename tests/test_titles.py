"""Blog title planning: unique, keyword-led stubs dated three days apart, shown under Content."""
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from test_report import StubReport
from test_web import DJANGO, WebCase, bundle

from companyscan import blog

if DJANGO:
    from django.contrib.auth.models import User
    from companyscan.web.models import BlogPost, Job, Site, sync

TODAY = date(2026, 10, 5)


def post(title, keyword="sourdough", abstract="Learn it."):
    return {"title": title, "abstract": abstract, "keyword": keyword, "tags": ["Bread", " baking ", ""]}


class PlanTests(unittest.TestCase):
    profile = {"keywords": ["sourdough", "rye"], "icp": "home bakers"}

    def run_plan(self, posts, existing=(), last=None, count=4):
        with patch.object(blog, "chat_model", return_value=StubReport({"posts": posts})) as chat:
            return blog.plan(self.profile, count, list(existing), last, today=TODAY), chat

    def test_drops_exact_and_near_duplicates_and_spaces_dates_three_days(self):
        stubs, _ = self.run_plan([post("Sourdough Starter Guide"), post("Guide to sourdough starter!"), post("Rye bread basics", "rye"),
                                  post("Sourdough starter guide today"), post("Why crumb matters")],
                                 existing=["Rye bread basics guide"])
        self.assertEqual([s["title"] for s in stubs], ["Sourdough Starter Guide", "Why crumb matters"])
        self.assertEqual([s["publish_on"] for s in stubs], [TODAY + timedelta(days=1), TODAY + timedelta(days=4)])
        self.assertEqual(stubs[0]["tags"], ["bread", "baking"])

    def test_continues_after_the_last_scheduled_date_and_never_in_the_past(self):
        future = self.run_plan([post("A")], last=TODAY + timedelta(days=10))[0]
        self.assertEqual(future[0]["publish_on"], TODAY + timedelta(days=13))
        stale = self.run_plan([post("A")], last=TODAY - timedelta(days=30))[0]
        self.assertEqual(stale[0]["publish_on"], TODAY + timedelta(days=1))

    def test_unknown_keyword_falls_back_and_prompt_targets_icp_and_keywords(self):
        stubs, chat = self.run_plan([post("A", keyword="made up")])
        self.assertEqual(stubs[0]["keyword"], "sourdough")
        user = chat.return_value.messages[1][1]
        self.assertIn("home bakers", user)
        self.assertIn('"rye"', user)
        self.assertIn("under 60 characters", chat.return_value.messages[0][1])

    def test_needs_keywords_and_ignores_malformed_rows(self):
        with self.assertRaisesRegex(ValueError, "keywords"):
            blog.plan({"keywords": []}, 4, [], None)
        self.assertEqual(self.run_plan(["junk", {"title": "", "abstract": "x"}, post("Ok")])[0][0]["title"], "Ok")


class ContentTests(WebCase):
    def setUp(self):
        super().setUp()
        bundle(self.root, "acme", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        sync()
        self.ann = User.objects.create_user("ann")
        self.site = Site.objects.get()
        self.site.user, self.site.keywords, self.site.icp = self.ann, "sourdough", "home bakers"
        self.site.save()
        self.client.force_login(self.ann)
        self.stub = StubReport({"posts": [post("Sourdough starter guide"), post("Why crumb matters")]})
        patcher = patch.object(blog, "chat_model", return_value=self.stub)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_plan_button_creates_dated_stubs_without_bodies_or_duplicates(self):
        self.client.post(f"/portal/content/plan/{self.site.pk}")
        stubs = list(BlogPost.objects.order_by("publish_on"))
        self.assertEqual([(s.status, s.body, s.title) for s in stubs], [("stub", "", "Sourdough starter guide"), ("stub", "", "Why crumb matters")])
        self.assertEqual((stubs[1].publish_on - stubs[0].publish_on).days, 3)
        self.assertEqual(self.job().kind, "titles")
        self.client.post(f"/portal/content/plan/{self.site.pk}")  # The same ideas again: all duplicates.
        self.assertEqual(BlogPost.objects.count(), 2)
        self.assertEqual(Job.objects.filter(state="error").count(), 1)

    def test_next_batch_continues_three_days_after_the_last_stub(self):
        self.client.post(f"/portal/content/plan/{self.site.pk}")
        last = BlogPost.objects.order_by("-publish_on").first().publish_on
        self.stub.reply = {"posts": [post("Rye starter tips", "sourdough")]}
        self.client.post(f"/portal/content/plan/{self.site.pk}")
        self.assertEqual(BlogPost.objects.order_by("-publish_on").first().publish_on, last + timedelta(days=3))

    def test_content_page_lists_upcoming_posts_in_date_order_for_the_owner_only(self):
        self.client.post(f"/portal/content/plan/{self.site.pk}")
        html = self.client.get("/portal/content").content.decode()
        self.assertLess(html.index("Sourdough starter guide"), html.index("Why crumb matters"))
        self.assertIn("Learn it.", html)
        self.client.force_login(User.objects.create_user("bob"))
        self.assertNotContains(self.client.get("/portal/content"), "Sourdough starter guide")
        self.assertEqual(self.client.post(f"/portal/content/plan/{self.site.pk}").status_code, 404)
