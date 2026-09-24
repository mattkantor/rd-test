import contextlib
import hashlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from companyscan.cli import main
from companyscan.dimensions import reputation
from companyscan.dimensions.reputation import ask_buyers, check_reputation, rank_reputation, write_bundle

# ScriptedLLM hands out each prompt's answers in call order, so these tests ask serially.
SERIAL = patch.object(reputation, "WORKERS", 1)
setUpModule, tearDownModule = SERIAL.start, SERIAL.stop


class StubLLM:
    """Duck-types the two LangChain chat model methods reputation uses."""

    def __init__(self, answer, analysis=None, fail_analysis=False):
        self.answer, self.analysis, self.fail_analysis, self.prompts = answer, analysis, fail_analysis, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.answer)

    def with_structured_output(self, schema):
        stub = self

        class Structured:
            def invoke(self, prompt):
                stub.prompts.append(prompt)
                if stub.fail_analysis:
                    raise RuntimeError("parse failed")
                return stub.analysis

        return Structured()


ANALYSIS = {"recognized": True, "inferred_icp": "Toronto families", "inferred_location": "Toronto, ON",
            "positioning_summary": "Well regarded", "sentiment": "positive",
            "competitors": [{"name": "Beta Dental", "website": "beta.test", "reason": "Same city"}]}


class ScriptedLLM:
    """Answers buyer questions from a script and extracts by schema title, so a whole ranking run is deterministic.
    Any scripted value that is an Exception is raised instead."""

    def __init__(self, analysis, answers, companies, generated=(), branded="Acme Dental (acme.test) is a Toronto dentist.", site=None):
        self.analysis, self.answers, self.companies, self.generated, self.branded = analysis, answers, companies, generated, branded
        self.site = site
        self.asked, self.structured = [], []

    @staticmethod
    def reply(value):
        if isinstance(value, Exception):
            raise value
        return value

    def invoke(self, prompt):
        self.asked.append(prompt)
        if prompt.startswith("What do you know"):
            return SimpleNamespace(content=self.branded)
        return SimpleNamespace(content=self.reply(self.answers[prompt].pop(0)))

    def with_structured_output(self, schema):
        llm = self

        class Structured:
            def invoke(self, prompt):
                llm.structured.append((schema["title"], prompt))
                if schema["title"] == "ReputationAnalysis":
                    return llm.reply(llm.analysis)
                if schema["title"] == "SiteIdentity":
                    return llm.reply(llm.site)
                if schema["title"] == "BuyerPrompts":
                    return {"prompts": list(llm.reply(llm.generated))}
                return {"companies": llm.reply(llm.companies.get(prompt.split("ANSWER:\n", 1)[1]))}

        return Structured()


ANSWER_A = "Try Acme Dental or Beta."
ANSWER_B = "Beta is the usual pick."
RANK_ANALYSIS = {**ANALYSIS, "target_sentiment": 0.9}
MENTIONS = {ANSWER_A: [{"name": "Acme Dental", "website": None, "position": 1, "sentiment": 0.6},
                       {"name": "Beta", "website": None, "position": 2, "sentiment": 0.2}],
            ANSWER_B: [{"name": "Beta", "website": None, "position": 1, "sentiment": 0.5}]}


class ReputationTest(unittest.TestCase):
    def test_records_raw_answer_and_analysis(self):
        answer = "Acme Dental (acme.test) serves Toronto families. Competitors: Beta Dental."
        llm = StubLLM(answer, ANALYSIS)
        record = check_reputation("https://acme.test/", llm, company_name="Acme Dental")
        self.assertIn("acme.test", llm.prompts[0])
        self.assertIn("Acme Dental", llm.prompts[0])
        self.assertIn(answer, llm.prompts[1])
        self.assertEqual(record["raw_answer"], answer)
        self.assertEqual(record["analysis"], ANALYSIS)
        self.assertTrue(record["domain_mentioned"])
        self.assertEqual(record["status"], "COMPLETE")

    def test_domain_not_mentioned(self):
        record = check_reputation("acme.test", StubLLM("I don't have information on that company.", {**ANALYSIS, "recognized": False}))
        self.assertFalse(record["domain_mentioned"])

    def test_list_content_blocks_are_joined(self):
        llm = StubLLM([{"type": "text", "text": "About acme.test"}, {"type": "text", "text": "."}], ANALYSIS)
        self.assertEqual(check_reputation("acme.test", llm)["raw_answer"], "About acme.test.")

    def test_failed_analysis_keeps_raw_answer(self):
        record = check_reputation("acme.test", StubLLM("acme.test is known", fail_analysis=True))
        self.assertEqual(record["status"], "PARTIAL")
        self.assertEqual(record["raw_answer"], "acme.test is known")
        self.assertIsNone(record["analysis"])
        self.assertIn("parse failed", record["error"])

    def test_bundle_writes_three_checksummed_files(self):
        result = rank_reputation("acme.test", ScriptedLLM(RANK_ANALYSIS, {"q1": [ANSWER_A]}, MENTIONS), "Acme Dental",
                                 prompts=["q1"], samples=1)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rep"
            summary = write_bundle(out, result, "openai:test")
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual([a["path"] for a in manifest["artifacts"]],
                             ["reputation/reputation.json", "reputation/answers.json", "reputation/scores.json"])
            for artifact in manifest["artifacts"]:
                self.assertEqual(hashlib.sha256((out / artifact["path"]).read_bytes()).hexdigest(), artifact["sha256"])
            scores = json.loads((out / "reputation/scores.json").read_text())
            self.assertEqual((scores["rank"], scores["of"], scores["model"]), (1, 2, "openai:test"))
            self.assertEqual(json.loads((out / "reputation/answers.json").read_text())["answers"][0]["raw_answer"], ANSWER_A)
            self.assertEqual(summary["status"], "COMPLETE")
            self.assertEqual((summary["rank"], summary["of"], summary["sentiment"]), (1, 2, 75))
            self.assertTrue(summary["domain_mentioned"])
            with self.assertRaises(ValueError):
                write_bundle(out, result, "openai:test")


class RankReputationTest(unittest.TestCase):
    def test_generated_prompts_are_filtered_deduped_and_sampled(self):
        generated = ["best family dentist in Toronto?", "is acme.test any good?", "Acme Dental reviews?",
                     "best family dentist in Toronto?", "  ", "affordable dentist downtown?"]
        llm = ScriptedLLM(RANK_ANALYSIS, {"best family dentist in Toronto?": [ANSWER_A, ANSWER_A],
                                          "affordable dentist downtown?": [ANSWER_B, ANSWER_B]}, MENTIONS, generated)
        result = rank_reputation("https://www.acme.test/", llm, "Acme Dental", samples=2)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["domain"], "acme.test")
        self.assertEqual(result["prompts"], [{"text": "best family dentist in Toronto?", "source": "generated"},
                                             {"text": "affordable dentist downtown?", "source": "generated"}])
        self.assertEqual([(a["prompt"], a["sample"]) for a in result["answers"]],
                         [("best family dentist in Toronto?", 1), ("best family dentist in Toronto?", 2),
                          ("affordable dentist downtown?", 1), ("affordable dentist downtown?", 2)])
        generation = next(p for title, p in llm.structured if title == "BuyerPrompts")
        self.assertIn("Toronto families", generation)
        self.assertIn("Toronto, ON", generation)
        self.assertEqual((result["scores"]["rank"], result["scores"]["of"], result["scores"]["mention_rate"]), (2, 2, 0.5))
        self.assertEqual(result["scores"]["sentiment"]["branded"]["score"], 90)

    def test_crawl_profile_catches_a_namesake(self):
        pages = [{"url": "https://acme.test/", "telephone_numbers": [], "links": [], "json_ld": {"documents": [
            {"@type": "Dentist", "name": "Acme Dental", "address": {"addressLocality": "Austin"}}]}}]
        denver = {**RANK_ANALYSIS, "stated_city": "Denver", "stated_category": "dentist"}
        answer = "Acme Dental in Denver is great, or Beta."
        mentions = {answer: [{"name": "Acme Dental", "website": None, "city": "Denver", "position": 1, "sentiment": 0.9},
                             {"name": "Beta", "website": None, "city": None, "position": 2, "sentiment": 0.2}]}
        result = rank_reputation("acme.test", ScriptedLLM(denver, {"q1": [answer]}, mentions), prompts=["q1"], samples=1, pages=pages)
        self.assertEqual(result["profile"]["names"], ["Acme Dental"])
        self.assertEqual(result["branded"]["identity"], {"verdict": "mismatch", "agree": ["category"], "echoed": [], "conflict": ["city"]})
        scores = result["scores"]
        self.assertEqual((scores["recognized"], scores["rank"], scores["visibility"]), (False, None, "not_found"))
        self.assertEqual(scores["sentiment"]["n"], 0)  # Neither the namesake's branded nor unbranded praise counts.
        austin = {**denver, "stated_city": "Austin"}
        result = rank_reputation("acme.test", ScriptedLLM(austin, {"q1": [ANSWER_A]}, MENTIONS), prompts=["q1"], samples=1, pages=pages)
        self.assertEqual(result["scores"]["identity"]["verdict"], "confirmed")
        self.assertEqual(result["scores"]["rank"], 1)

    def test_scores_survive_the_report_digest_trim(self):
        from companyscan.report.analyze import digest
        long = "x" * 60_000  # Raw answers far past the digest's per-file cap.
        llm = ScriptedLLM(RANK_ANALYSIS, {"q1": [long]}, {long: MENTIONS[ANSWER_A]})
        result = rank_reputation("acme.test", llm, "Acme Dental", prompts=["q1"], samples=1)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "technical").mkdir()
            (Path(tmp) / "technical/llm_reputation.json").write_text(json.dumps(result))
            text = digest(tmp)
        self.assertIn('"rank": 1', text)
        self.assertIn('"identity"', text)
        self.assertIn("[trimmed:", text)

    def test_site_read_fills_the_profile_audience_and_icp_check(self):
        text = "Acme Dental is a family dental practice in Austin. We care for kids and parents. Call 512-555-0100."
        page = lambda url, label, body: {"url": url, "classification": {"label": label}, "visible_text": body, "title": "t",
                                         "links": [], "json_ld": {"documents": []}, "telephone_numbers": []}
        pages = [page("https://acme.test/blog/1", "article", "Ten brushing tips."), page("https://acme.test/", "homepage", text),
                 page("https://acme.test/careers", "careers", ""), page("https://acme.test/about", "about", "Since 1999.")]
        site = {"company_name": "Acme Dental", "other_names": ["Acme Family Dental"], "category": "family dental practice",
                "offerings": ["cleanings"], "cities": ["Austin"], "service_area": "Austin, TX", "phones": ["512-555-0100"],
                "site_icp": "Austin families with kids", "icp_alignment": {"verdict": "misaligned", "reason": "Sells to families"},
                "evidence": [{"url": "https://acme.test/", "quote": "a family  dental practice in AUSTIN", "supports": "category"},
                             {"url": "https://acme.test/", "quote": "We fix teeth for dogs.", "supports": "offerings"}]}
        llm = ScriptedLLM({**RANK_ANALYSIS, "stated_city": "Austin"}, {"q?": [ANSWER_A]}, MENTIONS, ["q?"], site=site)
        result = rank_reputation("acme.test", llm, samples=1, pages=pages, icp="enterprise IT buyers")
        read = next(p for title, p in llm.structured if title == "SiteIdentity")
        # Homepage, then about, then the rest; empty pages skipped; the user's ICP is put to the check.
        self.assertLess(read.index("https://acme.test/\n"), read.index("https://acme.test/about"))
        self.assertLess(read.index("https://acme.test/about"), read.index("https://acme.test/blog/1"))
        self.assertNotIn("careers", read)
        self.assertIn('"enterprise IT buyers"', read)
        self.assertEqual(result["site_read"]["pages"], ["https://acme.test/", "https://acme.test/about", "https://acme.test/blog/1"])
        self.assertEqual([e["verified"] for e in result["site_read"]["identity"]["evidence"]], [True, False])
        self.assertEqual(result["profile"]["names"], ["Acme Dental", "Acme Family Dental"])
        self.assertEqual((result["profile"]["cities"], result["profile"]["phones"]), (["Austin"], ["5125550100"]))
        self.assertEqual(result["icp_check"], {"kind": "INFERRED", "user_icp": "enterprise IT buyers",
                                               "site_icp": "Austin families with kids", "verdict": "misaligned",
                                               "reason": "Sells to families"})
        self.assertEqual(result["audience"]["location"], {"value": "Austin, TX", "source": "site"})
        self.assertEqual(result["scores"]["identity"]["verdict"], "confirmed")  # The site-read city backs the branded answer.
        generation = next(p for title, p in llm.structured if title == "BuyerPrompts")
        self.assertIn("Looking for: family dental practice.", generation)
        self.assertEqual(result["status"], "COMPLETE")

    def test_site_read_without_user_icp_supplies_it_and_failure_is_partial(self):
        pages = [{"url": "https://acme.test/", "visible_text": "Dentist.", "links": [], "json_ld": {"documents": []}}]
        site = {"site_icp": "Toronto families", "icp_alignment": {"verdict": "not_checked", "reason": None}}
        llm = ScriptedLLM(RANK_ANALYSIS, {"q?": [ANSWER_A]}, MENTIONS, ["q?"], site=site)
        result = rank_reputation("acme.test", llm, samples=1, pages=pages)
        self.assertIn("not_checked", next(p for title, p in llm.structured if title == "SiteIdentity"))
        self.assertEqual(result["audience"]["icp"], {"value": "Toronto families", "source": "site"})
        self.assertIsNone(result["icp_check"])
        llm = ScriptedLLM(RANK_ANALYSIS, {"q?": [ANSWER_A]}, MENTIONS, ["q?"], site=RuntimeError("timeout"))
        result = rank_reputation("acme.test", llm, "Acme Dental", samples=1, pages=pages)
        self.assertEqual((result["status"], result["site_read"]["error"]), ("PARTIAL", "site read failed: timeout"))
        self.assertEqual(result["scores"]["rank"], 1)  # The rest of the check still ran.

    def test_user_prompts_skip_generation(self):
        llm = ScriptedLLM(RANK_ANALYSIS, {"q1": [ANSWER_B]}, MENTIONS)
        result = rank_reputation("acme.test", llm, prompts=["q1", "q1"], samples=1)
        self.assertNotIn("BuyerPrompts", [title for title, _ in llm.structured])
        self.assertEqual(result["prompts"], [{"text": "q1", "source": "user"}])
        self.assertIsNone(result["scores"]["rank"])
        self.assertEqual(result["status"], "COMPLETE")

    def test_failed_sample_and_empty_extraction_are_partial(self):
        llm = ScriptedLLM(RANK_ANALYSIS, {"q1": [ANSWER_A, RuntimeError("rate limited"), "odd answer"]}, MENTIONS)
        result = rank_reputation("acme.test", llm, "Acme Dental", prompts=["q1"], samples=3)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["scores"]["answers_scored"], 1)
        self.assertIn("rate limited", result["answers"][1]["error"])
        self.assertIn("no companies list", result["answers"][2]["error"])  # Structured call returned None.
        self.assertEqual(result["answers"][2]["raw_answer"], "odd answer")

    def test_generation_failure_keeps_branded(self):
        llm = ScriptedLLM(RANK_ANALYSIS, {}, MENTIONS, generated=RuntimeError("quota"))
        result = rank_reputation("acme.test", llm)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertTrue(result["error"].startswith("prompt generation failed"))
        self.assertEqual((result["prompts"], result["answers"], result["scores"]["rank"]), ([], [], None))
        self.assertEqual(result["branded"]["analysis"], RANK_ANALYSIS)

    def test_failed_branded_analysis_still_generates(self):
        llm = ScriptedLLM(RuntimeError("parse failed"), {"q?": [ANSWER_A]}, MENTIONS, generated=["q?"])
        result = rank_reputation("acme.test", llm, "Acme Dental", samples=1)
        generation = next(p for title, p in llm.structured if title == "BuyerPrompts")
        self.assertIn("unspecified", generation)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["scores"]["rank"], 1)

    def test_prompt_filter_matches_whole_words_only(self):
        generated = ["good dentist for kids?", "golf-friendly dentist?", "is go.com any good?", "Should I go with Go?"]
        llm = ScriptedLLM(RANK_ANALYSIS, {"good dentist for kids?": [ANSWER_B], "golf-friendly dentist?": [ANSWER_B]},
                          MENTIONS, generated)
        result = rank_reputation("go.com", llm, samples=1)
        self.assertEqual([p["text"] for p in result["prompts"]], ["good dentist for kids?", "golf-friendly dentist?"])

    def test_all_generated_prompts_dropped_is_explained(self):
        llm = ScriptedLLM(RANK_ANALYSIS, {}, MENTIONS, generated=["acme.test reviews?"])
        result = rank_reputation("acme.test", llm)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIn("no usable buyer questions", result["error"])

    def test_progress_counts_buyer_answers(self):
        calls = []
        llm = ScriptedLLM(RANK_ANALYSIS, {"q1": [ANSWER_A, ANSWER_B]}, MENTIONS)
        rank_reputation("acme.test", llm, prompts=["q1"], samples=2, progress=lambda *a: calls.append(a))
        self.assertEqual(calls, [(1, 2, "buyer answers"), (2, 2, "buyer answers")])

    def test_parallel_answers_keep_prompt_and_sample_order(self):
        class Slow:  # Earlier jobs finish last, so completion order is the reverse of input order.
            def invoke(self, prompt):
                time.sleep(0.05 if prompt.endswith("1") else 0)
                return SimpleNamespace(content=f"answer to {prompt}")

            def with_structured_output(self, schema):
                return SimpleNamespace(invoke=lambda prompt: {"companies": []})

        calls = []
        with patch.object(reputation, "WORKERS", 4):
            answers = ask_buyers(Slow(), ["q1", "q2"], 2, lambda *a: calls.append(a))
        self.assertEqual([(a["prompt"], a["sample"]) for a in answers], [("q1", 1), ("q1", 2), ("q2", 1), ("q2", 2)])
        self.assertEqual(calls[-1], (4, 4, "buyer answers"))


def fake_langchain(init_chat_model):
    """Stand-in for the optional `langchain.chat_models` package so CLI tests run without it."""
    package, chat_models = ModuleType("langchain"), ModuleType("langchain.chat_models")
    chat_models.init_chat_model, package.chat_models = init_chat_model, chat_models
    return patch.dict(sys.modules, {"langchain": package, "langchain.chat_models": chat_models})


class CliTest(unittest.TestCase):
    def command(self, args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(args)
        return code, json.loads(out.getvalue())

    def test_reputation_command_ranks_and_writes_bundle(self):
        models = []
        llm = ScriptedLLM(RANK_ANALYSIS, {"q1": [ANSWER_A], "q2": [ANSWER_B]}, MENTIONS)
        with tempfile.TemporaryDirectory() as tmp, fake_langchain(lambda m: models.append(m) or llm):
            Path(tmp, "prompts.txt").write_text("# buyer questions\n\nq2\n")
            out = Path(tmp, "out")
            code, result = self.command(["reputation", "acme.test", "--model", "openai:test", "--company-name", "Acme Dental",
                                         "--prompt", "q1", "--prompts-file", str(Path(tmp, "prompts.txt")),
                                         "--samples", "1", "--output", str(out), "--json"])
            answers = json.loads((out / "reputation/answers.json").read_text())
            self.assertEqual(json.loads((out / "manifest.json").read_text())["model"], "openai:test")
        self.assertEqual((code, result["status"], models), (0, "COMPLETE", ["openai:test"]))
        self.assertEqual(answers["prompts"], [{"text": "q1", "source": "user"}, {"text": "q2", "source": "user"}])
        self.assertEqual((result["rank"], result["of"], result["mention_rate"]), (2, 2, 0.5))

    def test_bad_prompt_inputs_are_json_errors(self):
        with tempfile.TemporaryDirectory() as tmp, fake_langchain(lambda m: StubLLM("x", ANALYSIS)):
            Path(tmp, "empty.txt").write_text("# only a comment\n\n")
            code, result = self.command(["reputation", "acme.test", "--prompts-file", str(Path(tmp, "empty.txt")), "--json"])
            self.assertEqual((code, result["status"]), (2, "ERROR"))
            self.assertIn("No prompts", result["error"])
            code, result = self.command(["reputation", "acme.test", "--prompts-file", str(Path(tmp, "missing.txt")), "--json"])
            self.assertEqual((code, result["status"]), (2, "ERROR"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
            main(["reputation", "acme.test", "--samples", "0", "--json"])
        self.assertEqual(exit_.exception.code, 2)
        self.assertIn("must be positive", json.loads(out.getvalue())["error"])

    def test_partial_analysis_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp, fake_langchain(lambda m: StubLLM("x", fail_analysis=True)):
            code, result = self.command(["reputation", "acme.test", "--output", tmp, "--json"])
        self.assertEqual((code, result["status"]), (1, "PARTIAL"))

    def test_errors_use_json_error_shape(self):
        def failing(model):
            raise RuntimeError("no OPENAI_API_KEY")

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "keep.txt").write_text("existing")
            with fake_langchain(failing):
                self.assertEqual(self.command(["reputation", "acme.test", "--output", tmp, "--json"])[1]["error"][:21], "Output path must be a")
                code, result = self.command(["reputation", "acme.test", "--output", str(Path(tmp, "new")), "--json"])
            self.assertEqual((code, result["status"]), (2, "ERROR"))
            self.assertIn("no OPENAI_API_KEY", result["error"])
            with patch.dict(sys.modules, {"langchain": None, "langchain.chat_models": None}):
                self.assertIn("pip install", self.command(["reputation", "acme.test", "--json"])[1]["error"])

    def test_pdf_command(self):
        with patch("companyscan.report.pdf.render_pdf", return_value=Path("/tmp/r.pdf")):
            self.assertEqual(self.command(["pdf", "bundle", "--json"]), (0, {"status": "COMPLETE", "pdf": str(Path("/tmp/r.pdf").resolve())}))
        with patch("companyscan.report.pdf.render_pdf", side_effect=ValueError("needs pandoc")):
            self.assertEqual(self.command(["pdf", "bundle", "--json"]), (2, {"status": "ERROR", "error": "needs pandoc"}))


if __name__ == "__main__":
    unittest.main()
