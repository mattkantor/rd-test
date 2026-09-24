# Reputation Ranking & Sentiment Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `companyscan reputation` and the `llm_reputation` dimension so they ask unbranded buyer questions and report a leaderboard rank and a −100..+100 sentiment score.

**Architecture:**
- **Scoring:** a new pure-Python module, `dimensions/ranking.py`, turns extracted answers into the leaderboard and sentiment numbers. It makes no LLM calls and has no I/O.
- **Flow:** `dimensions/reputation.py` gains the LLM side: buyer-question generation, sampling, per-answer extraction, `rank_reputation()` and a three-file bundle writer.
- **Wiring:** the CLI and the scan dimension both call `rank_reputation()`. The LLM is anything with `invoke()` and `with_structured_output(schema).invoke()`: a LangChain model, `ClaudeCode`, or a test stub.

**Tech Stack:** Python 3.10+ stdlib, `unittest`, optional LangChain (`.[llm]` extra, already present). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-23-reputation-ranking-design.md`

## Global Constraints

- No new dependencies. The core package stays dependency-free, and LangChain stays optional and lazily imported.
- Rank and sentiment are numbers. There is no PASS/WARNING/FAIL for this data anywhere.
- Sentiment is on a −100..+100 scale: round(mean × 100) of −1..1 ratings, and `null` when `n = 0`.
- Scoring is plain Python. The LLM only answers questions and extracts structure.
- Tests make no network calls. Run with: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
- This folder is not a git repo, so skip every commit step. The existing output conventions still apply: output directories must be new or empty, `--json` prints one JSON object, and exit codes are 0 complete, 1 partial, 2 error.

## Review Focus

1. **Malformed extraction values:** a null name, non-numeric or out-of-range sentiment, or missing position must be skipped or clamped, never crash. Pinned in Task 1.
2. **Structured call returns `None` or no list:** LangChain can return `None` on a parse failure. That is a per-answer error, not a crash. Pinned in Task 2.
3. **Duplicate or blank generated questions, or questions that name the target:** they are removed before sampling. Pinned in Task 2.
4. **Branded analysis failed:** question generation still runs with fallback ICP and location text. Pinned in Task 2.
5. **Unusable `--prompts-file` or `--samples 0`:** a missing file, a comment-only file or a non-positive count produces the standard JSON error with exit 2. Pinned in Task 3.

---

### Task 1: Pure scoring module

**Files:**
- Create: `src/companyscan/dimensions/ranking.py`
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `company_key(name: str, website: str | None = None) -> str`
  - `is_target(key: str, name: str, domain: str, company_name: str | None = None) -> bool`
  - `score(domain: str, answers: list[dict], company_name: str | None = None, branded_sentiment: float | None = None) -> dict`
  - Each answer is a dict with `companies` (a list of `{name, website, position, sentiment}`) and `error` (a string or None).
  - `score` returns `{rank, of, leaderboard: [{company, key, mentions, avg_position, is_target}], mention_rate, share_of_voice, sentiment: {score, n, min, max, branded: {...}, unbranded: {...}}, answers_total, answers_scored}`.
  - `domain` is the target host, lowercased, with no `www.`.

- [ ] **Step 1: Write the failing tests**

`tests/test_ranking.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_ranking -v`
Expected: ERROR `ModuleNotFoundError: No module named 'companyscan.dimensions.ranking'`

- [ ] **Step 3: Implement**

`src/companyscan/dimensions/ranking.py`:

```python
"""Leaderboard rank and sentiment score from extracted answers. Plain Python: the LLM answers and extracts, it never grades."""
from collections import Counter, defaultdict
from urllib.parse import urlsplit


def company_key(name, website=None):
    """Website host (lowercase, no www.) when given, else the lowercased name."""
    host = urlsplit(website if "//" in website else f"//{website}").hostname if website else None
    return (host or "").removeprefix("www.") or name.strip().lower()


def is_target(key, name, domain, company_name=None):
    # ponytail: exact domain/name/label match only; aliases like "Acme Inc" split. Add an alias list if that bites.
    squashed = name.strip().lower().replace(" ", "")
    names = {domain.split(".")[0], (company_name or "").lower().replace(" ", "")} - {""}
    return key == domain or squashed in names


def rating(value):
    """Clamp a model-reported sentiment to -1..1; anything non-numeric is no rating."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(-1.0, min(1.0, float(value)))


def summarize(ratings):
    if not ratings:
        return {"score": None, "n": 0, "min": None, "max": None}
    return {"score": round(sum(ratings) / len(ratings) * 100), "n": len(ratings),
            "min": round(min(ratings) * 100), "max": round(max(ratings) * 100)}


def order(mention):
    position = mention.get("position")
    return position if isinstance(position, (int, float)) and not isinstance(position, bool) else float("inf")


def score(domain, answers, company_name=None, branded_sentiment=None):
    """domain: target host without www. answers: rows with a `companies` list, or an `error`."""
    positions, names, unbranded = defaultdict(list), defaultdict(Counter), []
    scored = [a for a in answers if not a.get("error") and isinstance(a.get("companies"), list)]
    for answer in scored:
        seen = {}
        mentions = [c for c in answer["companies"] if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"].strip()]
        for c in sorted(mentions, key=order):
            key = company_key(c["name"], c.get("website"))
            key = domain if is_target(key, c["name"], domain, company_name) else key
            if key in seen:
                continue  # Named twice in one answer: counts once, at its first position.
            seen[key] = c
            positions[key].append(len(seen))
            names[key][c["name"].strip()] += 1
        if domain in seen and rating(seen[domain].get("sentiment")) is not None:
            unbranded.append(rating(seen[domain]["sentiment"]))
    board = sorted(({"company": names[k].most_common(1)[0][0], "key": k, "mentions": len(p),
                     "avg_position": round(sum(p) / len(p), 2), "is_target": k == domain} for k, p in positions.items()),
                   key=lambda r: (-r["mentions"], r["avg_position"], r["key"]))
    total, mine = sum(r["mentions"] for r in board), len(positions.get(domain, []))
    branded = [rating(branded_sentiment)] if rating(branded_sentiment) is not None else []
    return {"rank": next((i for i, r in enumerate(board, 1) if r["is_target"]), None), "of": len(board),
            "leaderboard": board,
            "mention_rate": round(mine / len(scored), 3) if scored else None,
            "share_of_voice": round(mine / total, 3) if total else None,
            "sentiment": {**summarize(branded + unbranded), "branded": summarize(branded), "unbranded": summarize(unbranded)},
            "answers_total": len(answers), "answers_scored": len(scored)}
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_ranking -v`
Expected: 6 tests OK.

---

### Task 2: Ranking flow (generation, sampling, extraction)

**Files:**
- Modify: `src/companyscan/dimensions/reputation.py`. Add `target_sentiment` to `ANALYSIS_SCHEMA`, and add `GENERATE`, `PROMPTS_SCHEMA`, `EXTRACT`, `MENTIONS_SCHEMA`, `structured`, `generate_prompts`, `ask_buyers` and `rank_reputation` after `check_reputation`.
- Test: `tests/test_reputation.py`. Add `ScriptedLLM`, fixtures and `RankReputationTest`.

**Interfaces:**
- Consumes: `score(domain, answers, company_name, branded_sentiment)` from Task 1, and the existing `check_reputation(domain, llm, company_name) -> dict` and `text(message) -> str`.
- Produces:
  - `rank_reputation(domain, llm, company_name=None, prompts=None, samples=3, num_prompts=8) -> dict`, returning `{status: "COMPLETE"|"PARTIAL", domain: str, error: str|None, branded: dict, prompts: [{text, source: "generated"|"user"}], answers: [{prompt, sample, asked_at, raw_answer, companies, error}], scores: dict}`.
  - Schema titles `"ReputationAnalysis"`, `"BuyerPrompts"` and `"CompanyMentions"`. The test stubs dispatch on these titles.

- [ ] **Step 1: Write the failing tests**

In `tests/test_reputation.py`, change the reputation import line to:

```python
from companyscan.dimensions.reputation import check_reputation, rank_reputation, write_bundle
```

Add after the `ANALYSIS = {...}` fixture:

```python
class ScriptedLLM:
    """Answers buyer questions from a script and extracts by schema title, so a whole ranking run is deterministic.
    Any scripted value that is an Exception is raised instead."""

    def __init__(self, analysis, answers, companies, generated=(), branded="Acme Dental (acme.test) is a Toronto dentist."):
        self.analysis, self.answers, self.companies, self.generated, self.branded = analysis, answers, companies, generated, branded
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
```

Add before `def fake_langchain`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_reputation.RankReputationTest -v`
Expected: ERROR `ImportError: cannot import name 'rank_reputation'`

- [ ] **Step 3: Implement**

In `src/companyscan/dimensions/reputation.py`:

Add the import after the existing relative imports:

```python
from .ranking import score
```

In `ANALYSIS_SCHEMA["properties"]`, add after `"sentiment"`:

```python
        "target_sentiment": {"type": ["number", "null"],
                             "description": "How the answer describes this company, -1 negative to 1 positive; null if not discussed"},
```

and append `"target_sentiment"` to `ANALYSIS_SCHEMA["required"]`.

Add after `check_reputation`:

```python
GENERATE = ("Write {n} different questions a buyer might ask an AI assistant when choosing a provider. Buyer: {icp}. "
            "Location: {location}. Ask for recommendations, shortlists or comparisons, the way a real buyer would. "
            "Never name or hint at a specific company, including {domain}.")

PROMPTS_SCHEMA = {"title": "BuyerPrompts", "description": "Unbranded buyer questions.", "type": "object",
                  "properties": {"prompts": {"type": "array", "items": {"type": "string"}}}, "required": ["prompts"]}

EXTRACT = ("List every company or product the answer below names or recommends, in the order they first appear. "
           "Give each its website if the answer states one, its 1-based position, and a sentiment from -1 (negative) "
           "to 1 (positive) for how the answer describes it. Use only the answer.\n\nANSWER:\n{answer}")

MENTIONS_SCHEMA = {
    "title": "CompanyMentions", "description": "Companies named in an answer, in order.", "type": "object",
    "properties": {"companies": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "website": {"type": ["string", "null"]}, "position": {"type": "integer"},
        "sentiment": {"type": "number"}}, "required": ["name", "website", "position", "sentiment"]}}},
    "required": ["companies"],
}


def structured(llm, schema, prompt, key):
    """Structured call that must return a list under `key`; LangChain can return None on a parse failure."""
    value = (llm.with_structured_output(schema).invoke(prompt) or {}).get(key)
    if not isinstance(value, list):
        raise ValueError(f"extraction returned no {key} list")
    return value


def generate_prompts(llm, domain, icp, location, n, company_name=None):
    prompt = GENERATE.format(n=n, icp=icp or f"customers of companies like the one at {domain}",
                             location=location or "unspecified", domain=domain)
    banned = [t.lower() for t in (domain, domain.split(".")[0], company_name) if t]
    kept = [p.strip() for p in structured(llm, PROMPTS_SCHEMA, prompt, "prompts") if isinstance(p, str) and p.strip()]
    return list(dict.fromkeys(p for p in kept if not any(t in p.lower() for t in banned)))[:n]


def ask_buyers(llm, prompts, samples):
    # ponytail: sequential calls; add a thread pool if runs get slow.
    answers = []
    for prompt in prompts:
        for number in range(1, samples + 1):
            row = {"prompt": prompt, "sample": number, "asked_at": now(), "raw_answer": None, "companies": None, "error": None}
            try:
                row["raw_answer"] = text(llm.invoke(prompt))
                row["companies"] = structured(llm, MENTIONS_SCHEMA, EXTRACT.format(answer=row["raw_answer"]), "companies")
            except Exception as exc:  # One failed sample is recorded and excluded; the rest still score.
                row["error"] = str(exc)
            answers.append(row)
    return answers


def rank_reputation(domain, llm, company_name=None, prompts=None, samples=3, num_prompts=8):
    """Branded check, then unbranded buyer questions sampled and scored into a rank and sentiment."""
    branded = check_reputation(domain, llm, company_name)
    host = branded["domain"].removeprefix("www.")
    analysis, error, source = branded["analysis"] or {}, None, "user" if prompts else "generated"
    if not prompts:
        try:
            prompts = generate_prompts(llm, host, analysis.get("inferred_icp"), analysis.get("inferred_location"),
                                       num_prompts, company_name)
        except Exception as exc:  # Keep the branded result; the rank is just unavailable.
            prompts, error = [], f"prompt generation failed: {exc}"
    prompts = list(dict.fromkeys(prompts))
    answers = ask_buyers(llm, prompts, samples)
    scores = score(host, answers, company_name, analysis.get("target_sentiment"))
    partial = branded["status"] != "COMPLETE" or error or not scores["answers_scored"] or any(a["error"] for a in answers)
    return {"status": "PARTIAL" if partial else "COMPLETE", "domain": host, "error": error, "branded": branded,
            "prompts": [{"text": p, "source": source} for p in prompts], "answers": answers, "scores": scores}
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_reputation.RankReputationTest tests.test_reputation.ReputationTest -v`
Expected: all OK. The existing `ReputationTest` still passes because `check_reputation` is unchanged.

---

### Task 3: Bundle, CLI flags and scan dimension

**Files:**
- Modify: `src/companyscan/dimensions/reputation.py`. Replace `LIMITATIONS`, `write_bundle` and `collect`.
- Modify: `src/companyscan/cli.py`. Add flags to the `reputation` subparser (near line 57) and replace the `reputation(args)` function (near line 116).
- Test: `tests/test_reputation.py`. Replace `test_bundle_is_checksummed_and_never_overwritten` and `test_reputation_command_writes_bundle`, and add a prompt-input error test.
- Test: `tests/test_dimensions.py`. Replace `LlmReputationTest.test_records_answer_and_models`.

**Interfaces:**
- Consumes: `rank_reputation(...) -> dict` from Task 2, and `positive()` in `cli.py`.
- Produces:
  - `write_bundle(output, result: dict, model: str) -> dict`, returning `{manifest, status, rank, of, mention_rate, share_of_voice, sentiment: int|None, domain_mentioned}`.
  - The dimension `collect` returns `{status, domain, error, branded, prompts, answers, scores, model, limitations}`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_reputation.py`, add `import hashlib` to the imports. Replace `test_bundle_is_checksummed_and_never_overwritten` with:

```python
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
```

In `CliTest`, replace `test_reputation_command_writes_bundle` with:

```python
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
```

In `tests/test_dimensions.py`, replace `LlmReputationTest.test_records_answer_and_models` with:

```python
    def test_ranks_through_claude_code(self):
        def fake_run(cmd, **kwargs):
            usage = {"modelUsage": {"claude-x": {}}}
            if "--json-schema" not in cmd:
                branded = cmd[2].startswith("What do you know")
                return completed({"result": "Acme Dental (acme.test) is a dentist" if branded else "Try Acme Dental or Beta.", **usage})
            title = json.loads(cmd[cmd.index("--json-schema") + 1])["title"]
            output = {"ReputationAnalysis": {"recognized": True, "inferred_icp": "families", "inferred_location": "Toronto",
                                             "target_sentiment": 0.5, "competitors": []},
                      "BuyerPrompts": {"prompts": ["best family dentist in Toronto?"]},
                      "CompanyMentions": {"companies": [{"name": "Acme Dental", "website": None, "position": 1, "sentiment": 0.8},
                                                        {"name": "Beta", "website": None, "position": 2, "sentiment": 0.1}]}}[title]
            return completed({"structured_output": output, **usage})

        with patch.object(reputation.subprocess, "run", side_effect=fake_run):
            result = llm_reputation(None, DISCOVERY, [], "Acme Dental")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual((result["scores"]["rank"], result["scores"]["of"]), (1, 2))
        self.assertEqual(len(result["answers"]), 3)  # 1 generated question x 3 default samples.
        self.assertEqual(result["model"], ["claude-x"])
        self.assertTrue(result["branded"]["domain_mentioned"])
        self.assertTrue(result["limitations"])
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_reputation tests.test_dimensions -v`
Expected: FAIL/ERROR in the three replaced tests and the new error test. `write_bundle` still expects the old shape, `--prompt` is not recognized, and `collect` returns no `scores`.

- [ ] **Step 3: Implement the bundle and dimension**

In `src/companyscan/dimensions/reputation.py`, replace `LIMITATIONS`:

```python
LIMITATIONS = ["Scores come from a small sample of one model's answers on one date; answers vary between runs, models and phrasing",
               "ICP, location, positioning, competitors and sentiment are UNVERIFIED model claims, not evidence",
               "No web search or grounding; reflects model training data only",
               "Companies are matched by website domain or name, so aliases of one company may be counted separately",
               "Generated buyer questions reflect the model's own inferred ICP and location",
               "domain_mentioned is a literal substring check on the branded answer"]
```

Replace `write_bundle`:

```python
def write_bundle(output, result, model):
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output path must be an empty directory: {output}")
    stamp = {"schema_version": SCHEMA_VERSION, "model": model, "created_at": now()}
    files = {"reputation/reputation.json": {**result["branded"], "model": model},
             "reputation/answers.json": {**stamp, "prompts": result["prompts"], "answers": result["answers"]},
             "reputation/scores.json": {**stamp, "domain": result["domain"], **result["scores"]}}
    artifacts = []
    for path, value in files.items():
        write_json(output / path, value)
        data = (output / path).read_bytes()
        artifacts.append({"path": path, "media_type": "application/json", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schema_version": SCHEMA_VERSION, "command": "reputation", "input_url": result["domain"], "model": model,
                "created_at": stamp["created_at"], "status": result["status"], "error": result["error"],
                "artifacts": artifacts, "limitations": LIMITATIONS}
    write_json(output / "manifest.json", manifest)
    scores = result["scores"]
    return {"manifest": str((output / "manifest.json").resolve()), "status": result["status"],
            "rank": scores["rank"], "of": scores["of"], "mention_rate": scores["mention_rate"],
            "share_of_voice": scores["share_of_voice"], "sentiment": scores["sentiment"]["score"],
            "domain_mentioned": result["branded"]["domain_mentioned"]}
```

Replace `collect`:

```python
def collect(client, discovery, pages, brand):
    # ponytail: defaults mean ~50 `claude -p` calls per scan; lower num_prompts/samples here if scans get too slow.
    llm = ClaudeCode()
    name = None if brand == urlsplit(discovery["origin"]).hostname else brand
    try:
        result = rank_reputation(discovery["origin"], llm, name)
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, KeyError) as exc:
        return {"status": "UNKNOWN", "reason": "llm_request_failed", "error": str(exc), "limitations": LIMITATIONS}
    return {**result, "model": sorted(llm.models) or "claude-code default", "limitations": LIMITATIONS}
```

- [ ] **Step 4: Implement the CLI**

In `src/companyscan/cli.py`, after `rep.add_argument("--company-name")` add:

```python
    rep.add_argument("--prompt", action="append", default=[], help="Buyer question to ask (repeatable); replaces generated ones")
    rep.add_argument("--prompts-file", type=Path, help="Buyer questions, one per line; # comments and blank lines ignored")
    rep.add_argument("--samples", type=positive, default=3, help="Times each question is asked")
    rep.add_argument("--num-prompts", type=positive, default=8, help="Buyer questions to generate when none are given")
```

Replace the `reputation(args)` function:

```python
def reputation(args):
    from .dimensions.reputation import rank_reputation, write_bundle
    prompts = list(args.prompt)
    if args.prompts_file:
        lines = [line.strip() for line in args.prompts_file.read_text(encoding="utf-8").splitlines()]
        from_file = [line for line in lines if line and not line.startswith("#")]
        if not from_file:
            raise ValueError(f"No prompts in {args.prompts_file}")
        prompts += from_file
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:
        raise ValueError("reputation needs LangChain: pip install -e '.[llm]'") from exc
    output = args.output or Path("output") / f"{directory_name(args.target)}-reputation"
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output path must be an empty directory: {output}")
    try:
        result = rank_reputation(args.target, init_chat_model(args.model), args.company_name,
                                 prompts or None, args.samples, args.num_prompts)
    except Exception as exc:  # Provider/auth/network errors surface as the standard error shape.
        raise ValueError(f"LLM request failed: {exc}") from exc
    return write_bundle(output, result, args.model)
```

- [ ] **Step 5: Run the full suite and confirm it passes**

Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
Expected: all OK. If `test_partial_analysis_exits_one` or `test_errors_use_json_error_shape` fail, check whether they depended on the old `write_bundle` return shape (`analysis` key). If they did, assert on `status` and exit code instead; don't change behaviour.

---

### Task 4: Rubric and README

**Files:**
- Modify: `.agents/skills/footprint-analyze/references/llm_reputation.md` (full replacement)
- Modify: `README.md`, the `## Reputation (optional LLM)` section

**Interfaces:**
- Consumes: the `technical/llm_reputation.json` shape from Task 3: `{status, domain, error, branded, prompts, answers, scores, model, limitations}`.
- Produces: documentation only.

- [ ] **Step 1: Replace the rubric**

`.agents/skills/footprint-analyze/references/llm_reputation.md`:

```markdown
# LLM reputation

Source: `technical/llm_reputation.json`:
- `branded`: one model's answer to "what do you know about this company", with its extraction.
- `prompts` and `answers`: unbranded buyer questions, each asked several times, with the companies each answer named.
- `scores`: the leaderboard rank and sentiment computed from those answers.

The model answered without web search. Use the citation shape from [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs use an `R` prefix.

**This dimension reports scores, not verdicts.** Do not assign PASS/WARNING/FAIL. If `status` is `UNKNOWN`, say the LLM request failed and stop.

- **Rank:** report `scores.rank` of `scores.of` (e.g. "#3 of 9"), with `mention_rate`, `share_of_voice`, `answers_scored` and the number of questions. If `rank` is null, say the company was not named in any buyer answer.
- **Leaderboard:** name the companies ranked above the target, with their mention counts and average positions. These are the competitors a buyer is steered towards instead.
- **Sentiment:** report `scores.sentiment.score` (−100..+100) with `n`, the branded and unbranded split, and the min–max range. A null score means no answer discussed the company.
- **Evidence:** quote representative answers, both one that names the target and one that doesn't. Never paraphrase a model's answer into a stronger claim. Answers are OBSERVED *model claims*, not facts.
- **Accuracy:** compare the branded answer against the website comprehension pass (identity, offer, ICP, location). Note if the model described the company wrongly or confused it with another.
- **Limits:** the sample size, one model, one date, no web search, and entity matching by domain or name. Assistants with web search may answer differently.
- **Business angle:** buyers increasingly ask assistants for shortlists. A low rank or low mention rate means the company is missing from those shortlists, and the leaderboard shows who is recommended instead.

Add a `llm_reputation` object `{rank, of, mention_rate, share_of_voice, sentiment, top_competitors, summary, findings}` to `analysis.json` and an **AI reputation** section to `report.md`.
```

- [ ] **Step 2: Update the README section**

In `README.md`, replace the body of `## Reputation (optional LLM)` (everything up to the next `## ` heading) with:

````markdown
Ask an LLM how it ranks and describes a company. This is the only command that uses an LLM, and it is an optional extra:

```sh
python -m pip install -e '.[llm]'
OPENAI_API_KEY=... companyscan reputation https://example.com --json
companyscan reputation example.com --company-name "Example Co" --prompts-file buyer-questions.txt --samples 5
```

It runs in three steps:

1. **Branded question:** asks what the model knows about the company, and extracts the inferred ICP, location, competitors and a sentiment rating.
2. **Buyer questions:** unbranded questions that don't name the company. By default the model writes them from the inferred ICP and location (`--num-prompts`, default 8). `--prompt` (repeatable) or `--prompts-file` (one per line, `#` comments allowed) replace the generated set.
3. **Scoring:** each buyer question is asked `--samples` times (default 3), and every answer is extracted into the companies it names, in order.

Scoring is plain Python:
- **Rank:** a leaderboard across all answers, sorted by mentions, then by average list position. You get the company's rank (`#3 of 9`), mention rate and share of voice.
- **Sentiment:** a score from −100 to +100, averaged over the answers that mention the company and split into branded and unbranded.

There is no pass/fail.

`--model` takes any LangChain `provider:model` string (default `openai:gpt-4o-mini`). Output goes to `output/<host>-reputation/`:
- `reputation/reputation.json`: the branded answer
- `reputation/answers.json`: every question, raw answer and extraction
- `reputation/scores.json`: the rank, leaderboard and sentiment

These scores come from a small sample of one model on one date, with no web search, so treat them as indicators. If a sample fails, it is recorded and left out of the counts, and the run is marked `PARTIAL`. `--dimension llm_reputation` on `scan` runs the same flow through `claude -p` (about 50 calls with the defaults).
````

- [ ] **Step 3: Final check**

Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
Expected: all OK.
Run: `PYTHONPATH=src .venv/bin/python -m coverage run --source=src/companyscan -m unittest discover -s tests && .venv/bin/python -m coverage report -m | grep -E "ranking|reputation|TOTAL"`
Expected: `ranking.py` and `reputation.py` at 90% or higher.
