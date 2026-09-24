import unittest
from types import SimpleNamespace
from unittest.mock import patch

from companyscan.dimensions import jev_copy

CHROME = "Home About Contact"


def page(url, body, scored=True):
    return {"url": url, "visible_text": f"{CHROME}\n{body}",
            "copy_scores": {"ai_slop": {"score": 10 if scored else None}}}


def answer(slop):
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 600},
            "answers": {"ai_slop": {"type": "score", "score": slop, "confidence": 0.8, "probabilities": {"2": 1.0}},
                        "first_hand": {"type": "noul", "noul": 0.1}, "generic": {"type": "noul", "noul": 0.7}}}


class JevCopyTests(unittest.TestCase):
    def setUp(self):
        self.client = SimpleNamespace(config=SimpleNamespace(timeout=5), progress=lambda *a: None)
        self.pages = [page("https://a.test/", "Unlock seamless growth."), page("https://a.test/b", "We built a janky script in 2021."),
                      page("https://a.test/c", "Hi", scored=False), {"url": "https://a.test/d", "visible_text": CHROME, "duplicate_of": "x"}]

    def test_no_key_is_unknown_and_makes_no_calls(self):
        with patch.dict("os.environ", {"JEV_API_KEY": ""}), patch.object(jev_copy, "ask") as ask:
            data = jev_copy.collect(self.client, {}, self.pages, "Acme")
        self.assertEqual((data["status"], data["reason"]), ("UNKNOWN", "no_key"))
        ask.assert_not_called()

    def test_scores_scaled_chrome_stripped_and_failures_kept(self):
        sent = {}

        def fake(key, text, timeout, context):
            sent[text] = key
            if "janky" in text:
                raise OSError("timed out")
            return answer(2.0)
        with patch.dict("os.environ", {"JEV_API_KEY": "secret"}), patch.object(jev_copy, "ask", side_effect=fake):
            data = jev_copy.collect(self.client, {}, self.pages, "Acme")
        self.assertEqual(len(sent), 2)  # Unscored and duplicate pages are skipped.
        self.assertTrue(all(CHROME not in text for text in sent))  # Shared nav lines aren't judged.
        ok, failed = data["pages"]
        self.assertEqual(ok["ai_slop"], {"score": 50, "level": "MEDIUM", "confidence": 0.8, "probabilities": {"2": 1.0}})
        self.assertEqual((ok["first_hand"], ok["generic"], ok["model"]), (0.1, 0.7, "jev-1.13.0"))
        self.assertEqual(failed["error"], "timed out")
        self.assertEqual((data["status"], data["pages_judged"], data["pages_failed"], data["input_tokens"]), ("OBSERVED", 1, 1, 600))
        self.assertEqual(data["ai_slop"], {"median": 50, "high": 0, "medium": 1})
        self.assertNotIn("secret", repr(data))  # The key never enters the bundle.
