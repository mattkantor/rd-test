import unittest

from companyscan.dimensions.ranking import company_key, is_target, score


def mention(name, position, sentiment=0.0, website=None):
    return {"name": name, "website": website, "position": position, "sentiment": sentiment}


class KeyTest(unittest.TestCase):
    def test_website_host_beats_name(self):
        self.assertEqual(company_key("HubSpot", "https://www.HubSpot.com/pricing"), "hubspot.com")
        self.assertEqual(company_key("HubSpot", "hubspot.com"), "hubspot.com")
        self.assertEqual(company_key("  Beta Co ", None), "beta co")

    def test_target_by_domain_company_name_or_label(self):
        self.assertTrue(is_target("acme.test", "Whatever", "acme.test"))
        self.assertTrue(is_target("acme dental", "Acme Dental", "acme.test", "Acme Dental"))
        self.assertTrue(is_target("acme", "ACME", "acme.test"))
        self.assertFalse(is_target("beta", "Beta", "acme.test", "Acme Dental"))

    def test_same_name_on_another_domain_is_not_the_target(self):
        self.assertFalse(is_target("acme.com", "Acme", "acme.io"))
        self.assertTrue(is_target("acme.io", "acme.io", "acme.io"))  # Named by its domain, no website.
        self.assertFalse(is_target("acmedental.com", "Acme Dental", "acme.test", "Acme Dental"))


class ScoreTest(unittest.TestCase):
    def test_leaderboard_rank_rates_and_sentiment(self):
        answers = [
            {"companies": [mention("HubSpot", 1, 0.5, "hubspot.com"), mention("Acme Dental", 2, 0.8), mention("Beta", 3)], "error": None},
            {"companies": [mention("Beta", 1), mention("ACME", 2, 0.2, "www.acme.test")], "error": None},
            {"companies": [mention("HubSpot", 1, 0.1, "https://www.hubspot.com/"), mention("Beta", 2), mention("Beta", 3)], "error": None},
            {"companies": None, "error": "rate limited"},
        ]
        result = score("acme.test", answers, "Acme Dental", branded_sentiment=0.9)
        board = [(r["key"], r["mentions"], r["avg_position"]) for r in result["leaderboard"]]
        # Beta leads on mentions; HubSpot beats Acme on the tie by average position; Beta's repeat in answer 3 counts once.
        self.assertEqual(board, [("beta", 3, 2.0), ("hubspot.com", 2, 1.0), ("acme.test", 2, 2.0)])
        self.assertEqual((result["rank"], result["of"]), (3, 3))
        self.assertTrue(result["leaderboard"][2]["is_target"])
        self.assertEqual(result["leaderboard"][2]["company"], "Acme Dental")
        self.assertEqual(result["mention_rate"], 0.667)
        self.assertEqual(result["share_of_voice"], 0.286)
        self.assertEqual((result["answers_total"], result["answers_scored"]), (4, 3))
        self.assertEqual(result["sentiment"]["unbranded"], {"score": 50, "n": 2, "min": 20, "max": 80})
        self.assertEqual(result["sentiment"]["branded"], {"score": 90, "n": 1, "min": 90, "max": 90})
        self.assertEqual((result["sentiment"]["score"], result["sentiment"]["n"]), (63, 3))

    def test_unranked_target_has_no_sentiment(self):
        result = score("acme.test", [{"companies": [mention("Beta", 1)], "error": None}])
        self.assertEqual((result["rank"], result["of"], result["mention_rate"], result["share_of_voice"]), (None, 1, 0.0, 0.0))
        self.assertEqual(result["sentiment"], {"score": None, "n": 0, "min": None, "max": None,
                                               "branded": {"score": None, "n": 0, "min": None, "max": None},
                                               "unbranded": {"score": None, "n": 0, "min": None, "max": None}})

    def test_no_scored_answers(self):
        result = score("acme.test", [{"companies": None, "error": "boom"}])
        self.assertEqual((result["rank"], result["of"], result["mention_rate"], result["share_of_voice"]), (None, 0, None, None))

    def test_malformed_mentions_are_skipped_or_clamped(self):
        answers = [
            {"companies": [{"name": None, "position": 1}, {"name": "Acme", "website": None, "sentiment": 1.7, "position": None},
                           {"name": "Zed", "website": None, "sentiment": "high", "position": 1}, "junk"], "error": None},
            {"companies": [{"name": "acme", "sentiment": "great"}], "error": None},
        ]
        result = score("acme.test", answers)
        self.assertEqual([(r["key"], r["mentions"], r["avg_position"]) for r in result["leaderboard"]],
                         [("acme.test", 2, 1.5), ("zed", 1, 1.0)])  # Missing position sorts last in its answer.
        self.assertEqual(result["sentiment"]["unbranded"], {"score": 100, "n": 1, "min": 100, "max": 100})


    def test_bad_websites_fall_back_to_name(self):
        answers = [{"companies": [{"name": "Ann", "website": "[n/a]", "position": 1},
                                  {"name": "Bo", "website": 7, "position": 2}], "error": None}]
        self.assertEqual([r["key"] for r in score("acme.test", answers)["leaderboard"]], ["ann", "bo"])


if __name__ == "__main__":
    unittest.main()
