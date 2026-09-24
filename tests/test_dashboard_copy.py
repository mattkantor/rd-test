import json
import tempfile
import unittest
from pathlib import Path

from companyscan.scan.copy_scores import score_text
from companyscan.web.dashboard import load
from test_copy_scores import HARD_SELL, PLAIN, SLOP
from test_dashboard import full_bundle, write

from test_web import WebCase


def rescore(bundle, rel, text):
    """Give a fixture page real copy scores (the page file changes after hashing; integrity is not what's tested)."""
    page = json.loads((bundle / rel).read_text())
    page["copy_scores"] = score_text(text, brand="Acme")
    write(bundle, rel, page)
    return page["copy_scores"]


class DashboardCopyScoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = full_bundle(self.root)
        self.home = rescore(self.bundle, "pages/0001.json", SLOP + "\n" + "\n".join([HARD_SELL] * 3))
        self.about = rescore(self.bundle, "pages/0003.json", PLAIN)
        summary = {key: {"median": 50, "high": 1, "medium": 0, "pages": 2} for key in ("ai_slop", "marketing_bias")}
        write(self.bundle, "technical/copy-scores.json", summary)

    def tearDown(self):
        self.tmp.cleanup()

    def cards(self, sort="issues"):
        return {c["id"]: c for c in load(self.bundle, sort)["pages"]}

    def test_content_area_shows_both_scores_and_flags_high(self):
        slop, bias = self.home["ai_slop"], self.home["marketing_bias"]
        self.assertEqual(bias["level"], "HIGH")
        content = self.cards()["0001"]["areas"][0]
        self.assertEqual(content["name"], "Content")
        self.assertEqual(content["level"], "warning")
        self.assertTrue(content["summary"].startswith(f"Marketing bias {bias['score']} (high): "))
        details = "\n".join(content["details"])
        self.assertIn(f"AI slop {slop['score']} ({slop['level']})", details)
        self.assertIn("stock phrases:", details)
        self.assertIn("“", details)  # A quoted example from the page.
        self.assertIn("sentence-length variation", details)
        self.assertIn("(lowers the score)", details)
        self.assertNotIn("matchs", details)

        about = self.cards()["0003"]["areas"][0]
        low = self.about["ai_slop"]["score"]
        self.assertIn(f"AI slop {low} LOW", about["summary"])  # No problem: the scores sit in the summary line.

    def test_missing_and_unknown_scores(self):
        page = json.loads((self.bundle / "pages/0003.json").read_text())
        del page["copy_scores"]
        write(self.bundle, "pages/0003.json", page)
        self.assertIn("Copy scores: not collected in this run", self.cards()["0003"]["areas"][0]["details"])
        rescore(self.bundle, "pages/0003.json", "Too short.")
        self.assertIn("AI slop: too little copy to score", self.cards()["0003"]["areas"][0]["details"])

    def test_sort_by_scores_highest_first_unscored_last(self):
        self.assertEqual(list(self.cards("slop"))[:2], ["0001", "0003"])
        self.assertEqual(list(self.cards("bias"))[-1], "0002")  # Failed page has no score.
        self.assertIn(("slop", "AI slop"), load(self.bundle)["sorts"])

    def test_tiles_and_attention(self):
        m = load(self.bundle)
        tiles = {t["title"]: t for t in m["tiles"]}
        self.assertEqual((tiles["AI slop"]["value"], tiles["AI slop"]["status"]), (50, "1 HIGH"))
        self.assertEqual(tiles["Marketing bias"]["href"], "?sort=bias#pages")
        self.assertIn({"level": "warning", "text": "1 page scores HIGH for AI slop", "href": "?sort=slop#pages"}, m["attention"])



class DashboardCopyPageTest(WebCase):  # Skipped outside python manage.py test.
    def test_page_renders_scores_and_sort_links(self):
        home = rescore(full_bundle(self.root), "pages/0001.json", SLOP + "\n" + "\n".join([HARD_SELL] * 3))
        page = self.client.get("/run/acme?sort=slop")
        self.assertEqual(page.status_code, 200)
        self.assertIn('href="?sort=bias#pages"', page.text)
        self.assertIn(f"Marketing bias {home['marketing_bias']['score']} (high)", page.text)


if __name__ == "__main__":
    unittest.main()
