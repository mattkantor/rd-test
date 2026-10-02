import os
import unittest
from unittest.mock import patch

from companyscan.report import scorecard


class BrandTest(unittest.TestCase):
    def test_scorecard_names_obvious_choice_systems_by_default(self):
        with patch.dict(os.environ, {"COMPANYSCAN_SERVICE_NAME": "", "COMPANYSCAN_SERVICE_PITCH": ""}):
            service = scorecard.service()
        self.assertEqual(service["name"], "Obvious Choice Systems")
        self.assertIn("Obvious Choice Systems", service["pitch"])
        self.assertNotIn("DrGrow", service["pitch"])
        with patch.dict(os.environ, {"COMPANYSCAN_SERVICE_NAME": "Acme Growth"}):
            self.assertEqual(scorecard.service()["name"], "Acme Growth")  # Still overridable.
