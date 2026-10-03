import unittest

from companyscan.scan import social_proof
from companyscan.scan.extract import extract

QUOTE = "On my call with Matt, we productively addressed a huge range of issues in a single half-hour."


def page(url="https://acme.test/", **fields):
    base = {"url": url, "visible_text": "", "headings": [], "links": [], "script_sources": [], "json_ld": {"types": []},
            "testimonials": [], "quotation_candidates": [], "classification": {"label": "other"}, "trustpilot_widgets": []}
    return {**base, **fields}


class SocialProofTest(unittest.TestCase):
    def kinds(self, result):
        return set(result["signals"])

    def test_quotes_like_a_real_site_are_proof(self):
        result = social_proof.check([page(visible_text=f"In their words.\nChris, SaaS founder“{QUOTE}”")])
        self.assertEqual(self.kinds(result), {"testimonial_section", "attributed_quote"})
        self.assertEqual((result["has_proof"], result["has_ask"], result["status"]), (True, False, "WARNING"))
        self.assertEqual(result["pages_with_proof"], ["https://acme.test/"])

    def test_asks_for_reviews_and_referrals(self):
        result = social_proof.check([page(
            links=[{"url": "https://search.google.com/local/writereview?placeid=X1", "text": "Review us on Google"},
                   {"url": "https://acme.test/contact", "text": "Share your experience"}],
            visible_text="Know someone who needs us? Refer a friend and you both save.")])
        self.assertEqual(self.kinds(result), {"review_link", "testimonial_ask", "referral_ask"})
        self.assertEqual((result["has_proof"], result["has_ask"], result["status"]), (False, True, "WARNING"))

    def test_both_pass_and_neither_fails(self):
        both = page(json_ld={"types": ["Review"]}, links=[{"url": "https://acme.test/review", "text": "Leave a review"}])
        self.assertEqual(social_proof.check([both])["status"], "PASS")
        self.assertEqual(social_proof.check([page(visible_text="We build websites.")])["status"], "FAIL")
        self.assertEqual(social_proof.check([])["status"], "UNKNOWN")

    def test_nav_labels_and_unattributed_quotes_are_not_proof(self):
        result = social_proof.check([page(
            links=[{"url": "https://acme.test/reviews", "text": "Reviews"}],  # A menu label, also in the page text.
            visible_text=f'Home\nReviews\nAs the saying goes, "{QUOTE}" That is how we think about planning.')])
        self.assertFalse(result["has_proof"])
        negated = social_proof.check([page(visible_text="Investigations, not testimonials.")])
        self.assertNotIn("testimonial_section", negated["signals"])  # A line saying it isn't one.

    def test_widgets_and_trustpilot_on_the_site(self):
        result = social_proof.check([page(
            script_sources=["https://widget.trustpilot.com/bootstrap/v5/tp.widget.bootstrap.min.js"],
            links=[{"url": "https://www.trustpilot.com/review/acme.test", "text": "See our reviews"}],
            visible_text="Rated 4.8 out of 5 on Trustpilot from 1,203 reviews.\nWe're also on Trustpilot.")])
        self.assertEqual(result["trustpilot"], {"widget": True, "profile_link": "https://www.trustpilot.com/review/acme.test",
                                                "review_link": None, "score_text": "Rated 4.8 out of 5 on Trustpilot from 1,203 reviews"})
        self.assertIn("review_widget", self.kinds(result))
        self.assertIn("rating_text", self.kinds(result))
        self.assertEqual(result["profiles"], {"Trustpilot": "https://www.trustpilot.com/review/acme.test"})
        bare = social_proof.check([page(visible_text="We're on Trustpilot.")])
        self.assertIsNone(bare["trustpilot"]["score_text"])  # Names Trustpilot but holds no rating.

    def test_examples_are_short_and_few(self):
        long_quote = "word " * 100
        pages = [page(url=f"https://acme.test/{i}", visible_text=f"Jane Doe, CEO“{long_quote}”") for i in range(15)]
        result = social_proof.check(pages)
        self.assertEqual(len(result["examples"]), social_proof.EXAMPLES)
        self.assertTrue(all(len(e["example"]) <= social_proof.EXAMPLE_MAX for e in result["examples"]))

    def test_wrong_shaped_pages_dont_crash(self):
        result = social_proof.check([{"url": "https://acme.test/"}, {"url": "x", "visible_text": None, "links": ["bad"],
                                                                     "headings": "h", "json_ld": []}])
        self.assertEqual(result["status"], "FAIL")

    def test_extractor_records_trustpilot_widgets(self):
        html = ('<html><body><div class="trustpilot-widget" data-businessunit-id="5419b6a8" '
                'data-template-id="t1" data-style-height="24px"></div></body></html>')
        self.assertEqual(extract(html, "https://acme.test/")["trustpilot_widgets"],
                         [{"businessunit_id": "5419b6a8", "template_id": "t1", "style_height": "24px"}])
        result = social_proof.check([page(trustpilot_widgets=[{"businessunit_id": "5419b6a8"}])])
        self.assertTrue(result["trustpilot"]["widget"])


class SocialProofReportTest(unittest.TestCase):
    def test_rubric_is_shipped_and_named_in_the_skill(self):
        from pathlib import Path
        from companyscan.report.analyze import SKILL, rubrics
        self.assertIn("social_proof.md", SKILL.read_text())
        self.assertTrue((SKILL.parent / "references/social_proof.md").exists())
        self.assertIn("# references/social_proof.md", rubrics(Path("/nonexistent")))  # Always applies.

    def test_scorecard_explains_social_proof(self):
        from companyscan.report import scorecard
        self.assertIn("Buyers trust other customers", scorecard.WHY["social_proof"])
        self.assertEqual(scorecard.LABELS["social_proof"], "Social proof")
