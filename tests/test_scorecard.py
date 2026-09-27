"""Customer scorecard: scores from verdicts, dollars from the growth goal, everything model-written escaped."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from companyscan.report import scorecard

ANALYSIS = {
    "source_manifest": {"path": "manifest.json"}, "coverage": {"limitations": []},
    "findings": [{"id": "F1", "title": "No pricing page", "severity": "FAIL", "interpretation": "Buyers can't compare.",
                  "business_impact": {"headline": "<b>Buyers leave</b> before calling"}},
                 {"id": "F2", "title": "Clear services", "severity": "PASS"},
                 {"id": "G1", "title": "Phone differs", "severity": "FAIL"}],
    "google_business": {"verdict": "FAIL", "summary": "Listing phone differs.", "findings": ["G1", {"id": "G2", "severity": "WARNING"}]},
    "technical_marketing": {"aeo": {"verdict": "PASS", "summary": "Schema is sound."}, "measurement": {"verdict": "WARNING"}},
    "copy": {"icp_consistency": {"verdict": "PASS"}, "findings": []},
    "meta_ads": {"verdict": "UNKNOWN", "summary": "Not configured."},
    "business_impact_summary": {"ranked": ["F1", "missing"]},
}


class ScorecardTest(unittest.TestCase):
    def test_scores_areas_and_prices_the_gap(self):
        card = scorecard.build(ANALYSIS, ltv=2000, customers=10)
        areas = {a["key"]: a for a in card["areas"]}
        self.assertEqual(list(areas), ["website", "google_business", "technical_marketing", "copy", "meta_ads"])
        self.assertEqual((areas["copy"]["score"], areas["copy"]["summary"]), (100, "ICP consistency: PASS."))
        self.assertEqual(areas["website"]["score"], 50)  # F1 fail + F2 pass; G1 is claimed by ID by the Google area.
        self.assertEqual((areas["google_business"]["score"], areas["google_business"]["counts"]), (25, {"FAIL": 1, "WARNING": 1}))
        self.assertEqual(areas["technical_marketing"]["score"], 75)  # From its sub-verdicts: no findings.
        self.assertEqual(areas["technical_marketing"]["summary"], "Schema is sound. Measurement: WARNING.")
        self.assertIsNone(areas["meta_ads"]["score"])  # UNKNOWN isn't scored or averaged.
        self.assertEqual(card["overall"], 62)  # (50 + 25 + 75 + 100) / 4.
        self.assertEqual((card["goal"], card["at_risk"]), (20000, 7600))
        self.assertEqual([areas[k]["at_risk"] for k in ("website", "google_business", "technical_marketing", "copy")], [2533, 3800, 1267, 0])
        self.assertEqual(card["costliest"], ["<b>Buyers leave</b> before calling"])

    def test_no_dollars_without_both_goal_fields(self):
        self.assertIsNone(scorecard.build(ANALYSIS, ltv=2000)["at_risk"])
        self.assertIsNone(scorecard.build({"findings": []})["overall"])

    def test_html_escapes_model_text(self):
        page = scorecard.html(scorecard.build(ANALYSIS, 2000, 10), "acme.test", "2026-09-01T00:00:00+00:00")
        self.assertIn("&lt;b&gt;Buyers leave&lt;/b&gt;", page)
        self.assertNotIn("<b>Buyers leave", page)
        self.assertIn("$7,600", page)
        self.assertIn("1 needs the most work: Google listing.", page)
        self.assertIn("1 failed · 1 warning", page)
        self.assertIn("not a forecast", page)
        self.assertIn("Add customer lifetime value", scorecard.html(scorecard.build(ANALYSIS), "acme.test", ""))

    def test_render_needs_a_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "manifest.json").write_text(json.dumps({"input_url": "https://acme.test/", "created_at": "2026-09-01"}))
            with self.assertRaisesRegex(ValueError, "generate the report first"):
                scorecard.render_scorecard(bundle)
            (bundle / "analysis").mkdir()
            (bundle / "analysis/analysis.json").write_text(json.dumps(ANALYSIS))
            with patch.object(scorecard, "chrome_path", lambda: "chrome"), \
                    patch.object(scorecard, "print_pdf", lambda chrome, html, pdf: pdf.write_bytes(b"%PDF")):
                pdf = scorecard.render_scorecard(bundle, 2000, 10)
            self.assertEqual(pdf, (bundle / "analysis/scorecard.pdf").resolve())
            self.assertIn("acme.test", (bundle / "analysis/scorecard.html").read_text())


if __name__ == "__main__":
    unittest.main()
