import unittest

from companyscan.scan.copy_scores import MIN_WORDS, score_pages, score_text

SLOP = """In today's fast-paced landscape, we help you unlock seamless growth. It's not just marketing, it's a journey.
Whether you're a startup or an enterprise, our robust platform empowers teams to elevate results — seamlessly.
Let's dive in. We leverage cutting-edge tools to streamline workflows. Our holistic approach fosters synergy.
Moreover, this transformative solution is a testament to innovation. Here's the thing: the landscape is ever-evolving.
We delve into data to unlock insight — and we elevate brands. It's important to note that results matter to everyone.
Our comprehensive, innovative, and dynamic team harnesses robust strategies. Furthermore, we streamline everything.
Unlock growth today. Elevate your brand. Leverage our expertise. Empower your people. Streamline the journey now."""

PLAIN = """I ran the numbers for a 12-person clinic in Guelph last March. They booked 41 new patients from 3,200 postcards,
which cost $1,900 to print and mail. The front desk tracked every call on a paper sheet taped beside the phone.
Two things surprised me. Most calls came on Tuesday mornings, and the older patients asked about parking before
anything else, so we moved the parking note to the top of the card. The next batch of 3,000 cards brought in 57 patients.
That is not a huge jump, and part of it was probably the season. If your practice is already full, this won't help.
You would get more from fixing the phone greeting, which lost roughly one caller in five when we listened to recordings."""

HARD_SELL = """We are the leading, world-class, #1 agency and the best in the industry. Our award-winning experts are trusted by
10,000+ companies. We guarantee 300% growth. Act now: this is a limited-time offer and only 3 spots left this month.
Don't miss out, your competitors are already using us. Join 10,000+ brands before it's too late. Every day you wait,
you're losing money and leaving money on the table. Our certified team has 20 years of experience. We always deliver.
We built our platform, our process and our people to be the best. We are featured in Forbes and as seen on TV.
Stop losing deals. Our revolutionary method is unmatched and second to none. We are the only agency you need."""

BALANCED = """You probably don't need an agency. If your list is under 500 contacts, you'll get more from writing to them yourself,
and you should. Here is how you can tell. Your reply rate on the last campaign tells you whether the list or the
message is the problem. You can test that in a week. This isn't for everyone: if you sell to fewer than 50 accounts,
we are not a fit, and we will say so on the first call. The trade-off with doing it yourself is time, roughly
four hours a week. The downside of hiring us is cost and a slower start while you and your team review the drafts."""


def unique(text, i):
    """Same copy, but no line or line opening shared with other pages (so none of it reads as chrome or skeleton)."""
    return "\n".join(f"{'abcdefgh'[i] * 4} {line}" for line in text.splitlines())  # Letters: openings ignore digits.


def page(url, text, label="other"):
    return {"url": url, "visible_text": text, "classification": {"label": label}}


class CopyScoresTests(unittest.TestCase):
    def test_slop_scores_high_with_quoted_evidence(self):
        slop, plain = score_text(SLOP)["ai_slop"], score_text(PLAIN)["ai_slop"]
        self.assertEqual(slop["level"], "HIGH")
        self.assertEqual(plain["level"], "LOW")
        self.assertIn("stock_phrases", slop["top_signals"])
        stock = slop["signals"]["stock_phrases"]
        self.assertGreaterEqual(stock["count"], 20)
        self.assertTrue(any("unlock" in e.lower() for e in stock["examples"]))
        self.assertEqual(slop["signals"]["contrast_frames"]["count"], 1)
        self.assertGreater(plain["signals"]["specificity"]["subscore"], 0)

    def test_uniform_rhythm_scores_higher_than_varied(self):
        uniform = " ".join(["The team shipped the new pricing page this week."] * 12)
        varied = " ".join(["We shipped.", "The pricing page went live on Tuesday after three rounds of review with sales.",
                           "Fine.", "Nobody expected the enterprise tier to be the one prospects asked about most often, but it was.",
                           "So we rewrote it twice.", "Calls went up.", "The team, tired but pleased, took Friday off.",
                           "Next quarter we will look at onboarding.", "Maybe.", "Probably the checklist first, then the emails."] * 2)
        rhythm = lambda t: score_text(t * 3)["ai_slop"]["signals"]["rhythm"]
        self.assertGreater(rhythm(uniform)["subscore"], rhythm(varied)["subscore"])
        self.assertEqual(rhythm(uniform)["subscore"], 100)

    def test_template_placeholders_found_even_in_shared_chrome(self):
        filler = "This Headline Grabs Visitors’ Attention\n"
        pages = [page(f"https://a.test/{i}", filler + unique(PLAIN, i)) for i in range(4)]
        score_pages(pages)
        slop = pages[0]["copy_scores"]["ai_slop"]
        self.assertEqual(pages[0]["copy_scores"]["chrome_lines_removed"], 1)
        self.assertEqual(slop["signals"]["template_artifacts"]["count"], 1)
        self.assertGreaterEqual(slop["score"], 40)

    def test_hard_sell_bias_breakdown(self):
        bias = score_text("\n".join([HARD_SELL] * 3), brand="Acme")["marketing_bias"]  # 300+ words: balance expected.
        self.assertEqual(bias["level"], "HIGH")
        s = bias["signals"]
        for lever in ("unsupported_claims", "pressure", "fomo", "loss_aversion", "authority", "self_focus", "one_sidedness"):
            self.assertGreater(s[lever]["subscore"], 0, lever)
        self.assertTrue(any("#1" in e for e in s["unsupported_claims"]["examples"]))
        self.assertTrue(any("only 3 spots" in e for e in s["pressure"]["examples"]))
        self.assertTrue(s["self_focus"]["opens_on_self"])

    def test_reader_focused_balanced_copy_scores_low(self):
        bias = score_text(BALANCED)["marketing_bias"]
        self.assertEqual(bias["level"], "LOW")
        self.assertLess(bias["signals"]["self_focus"]["subscore"], score_text(HARD_SELL)["marketing_bias"]["signals"]["self_focus"]["subscore"])
        self.assertGreater(bias["signals"]["one_sidedness"]["count"], 0)

    def test_sourced_and_measured_stats_are_not_unsupported(self):
        filler = " ".join(["The clinic reviewed its intake forms with the front desk staff every Monday morning."] * 8)
        text = filler + " Reply rates rose 40% according to a 2025 survey. Conversion went from 0.97% to 2.73% after the change."
        self.assertEqual(score_text(text)["marketing_bias"]["signals"]["unsupported_claims"]["count"], 0)
        self.assertEqual(score_text(filler + " Reply rates rose 40% last year.")["marketing_bias"]["signals"]["unsupported_claims"]["count"], 1)

    def test_brand_name_is_not_puffery(self):
        text = " ".join(["Best Leads books meetings for recruitment firms in Toronto and nearby cities each quarter."] * 8)
        self.assertEqual(score_text(text, brand="Best Leads")["marketing_bias"]["signals"]["unsupported_claims"]["count"], 0)
        self.assertGreater(score_text(text)["marketing_bias"]["signals"]["unsupported_claims"]["count"], 0)

    def test_short_failed_and_duplicate_pages(self):
        pages = [page("https://a.test/short", "Contact us today."), {"url": "https://a.test/broken", "error": "HTTP 500"},
                 {**page("https://a.test/dupe", PLAIN), "duplicate_of": "https://a.test/"}, page("https://a.test/", PLAIN)]
        summary = score_pages(pages)
        self.assertEqual(pages[0]["copy_scores"]["ai_slop"]["level"], "UNKNOWN")
        self.assertIsNone(pages[0]["copy_scores"]["marketing_bias"]["score"])
        self.assertIn(str(MIN_WORDS), pages[0]["copy_scores"]["ai_slop"]["note"])
        self.assertNotIn("copy_scores", pages[1])
        self.assertNotIn("copy_scores", pages[2])
        self.assertEqual((summary["pages_scored"], summary["pages_unscored"]), (1, 1))

    def test_shared_skeleton_and_site_summary(self):
        body = "Key takeaways from this engagement\nThe short answer is that the list was wrong\n"
        pages = [page(f"https://a.test/post-{i}", body.replace("engagement", f"engagement {i}").replace("list", f"list {i}")
                      + unique(PLAIN, i), "article") for i in range(5)]
        pages.append(page("https://a.test/", HARD_SELL, "homepage"))
        summary = score_pages(pages)
        skeleton = pages[0]["copy_scores"]["ai_slop"]["signals"]["formula_skeleton"]
        self.assertEqual(skeleton["count"], 2)
        self.assertIn("key takeaways from", summary["skeleton_openings"])
        self.assertEqual(summary["marketing_bias"]["top_pages"][0]["url"], "https://a.test/")
        self.assertEqual(set(summary["ai_slop"]["by_page_type"]), {"article", "homepage"})
        self.assertEqual(len(summary["pages"]), 6)


if __name__ == "__main__":
    unittest.main()
