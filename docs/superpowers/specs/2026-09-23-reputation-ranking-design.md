# Reputation ranking and sentiment score: design

Date: 2026-09-23 · Status: approved in chat, awaiting spec review

## Goal

Measure how an LLM ranks a company against its competitors when buyers ask unbranded questions, and how positively it talks about the company. The result is **two numbers with evidence behind them: a leaderboard rank and a sentiment score from −100 to +100.** It is not PASS/FAIL.

The single branded check (`check_reputation`) that exists today records what the model says, but cannot rank the company. It names the company in the prompt, uses one question, and takes one sample.

## Decisions

| Topic | Decision |
|---|---|
| Surface | Extend the existing `companyscan reputation` command and the `llm_reputation` dimension. No new command. |
| Buyer questions | Generated from the inferred ICP and location by default. `--prompt` (repeatable) and `--prompts-file` replace the generated set. |
| Ranking | Leaderboard rank across all unbranded answers, e.g. `#3 of 9`. Mention rate, share of voice and average list position are shown beside it. |
| Sentiment | Each answer that mentions the target is rated −1..+1, averaged and scaled to −100..+100. Branded and unbranded answers are also reported separately, each with `n` and a range. |
| Verdicts | None for this data. The `llm_reputation.md` rubric changes from PASS/WARNING/FAIL to reporting the scores. |

## CLI

```sh
companyscan reputation <domain> [--model openai:gpt-4o-mini] [--company-name NAME]
  [--prompt TEXT]... [--prompts-file FILE] [--samples 3] [--num-prompts 8] [--output DIR] [--json]
```

- `--prompts-file`: one question per line; blank lines and lines starting with `#` are ignored.
- If you supply questions (with `--prompt`, `--prompts-file` or both), they are combined and the generation step is skipped.
- `--samples` and `--num-prompts` must be positive (reuse `positive()` from `cli.py`).
- The dimension path (`--dimension llm_reputation` on scan) uses the defaults and `ClaudeCode` as the LLM.

## Flow (`dimensions/reputation.py`)

Every step takes `llm`: any object with `invoke(prompt)` and `with_structured_output(schema).invoke(prompt)`. That covers LangChain chat models, `ClaudeCode`, and the test stub.

1. **Branded:** the existing `check_reputation`. It provides the raw answer, the analysis (ICP, location, competitors, sentiment label) and `domain_mentioned`. Its extraction schema gains `target_sentiment` (a number from −1 to 1, or null if the target isn't discussed).
2. **Question generation:** skipped if the user supplied questions. Otherwise one structured call returns `{"prompts": [str]}` of length `num_prompts`: realistic buyer questions for the inferred ICP and location. The instruction forbids naming the target. As a guard, any generated question that contains the target's domain or name is dropped.
3. **Sampling:** ask each question `samples` times through `llm.invoke`, sequentially, and record every raw answer.
4. **Extraction:** one structured call per answer, returning `{"companies": [{"name", "website", "position", "sentiment"}]}`. `position` is the 1-based order in which the company appears in the answer, and `sentiment` runs from −1 to 1.
5. **Scoring (`score(target, branded, answers)`): plain Python, no LLM.**
   - **Company key:** the host of `website`, lowercased and without `www.`, if present. Otherwise the lowercased, trimmed `name`.
   - **Target match:** the key equals the target domain, or the lowercased name equals `--company-name`, or the lowercased name equals the domain's main label (e.g. `bestleads` for `bestleads.io`).
   - **Leaderboard:** for each company key, the number of answers naming it and its average position. A company named more than once in the same answer counts once, at its first position. Sorted by mentions descending, then average position ascending. Each row shows the most common display name.
   - `rank`: the target's 1-based place on the leaderboard, or `null` if it is unranked. `of`: the leaderboard length.
   - `mention_rate` = answers naming the target ÷ successful unbranded answers.
   - `share_of_voice` = the target's mentions ÷ all company mentions.
   - `sentiment.score` = round(mean × 100) over every successful answer (branded and unbranded) that mentions the target. For the branded answer the rating is `target_sentiment`; for an unbranded answer it is the `sentiment` on the target's company entry. The same is reported for `branded` and `unbranded`, each with `n` and `min`/`max`. The score is `null` when `n = 0`.

## Output bundle

```
output/<host>-reputation/
├── manifest.json
└── reputation/
    ├── reputation.json   # branded record (unchanged shape + target_sentiment)
    ├── answers.json      # prompts (with source: generated|user), every sample: prompt, raw answer, extraction, error
    └── scores.json       # rank, of, leaderboard, mention_rate, share_of_voice, sentiment, sample counts, model, date
```

- All three files go in the manifest with sha256 hashes.
- The command's JSON output adds `rank`, `of`, `mention_rate`, `share_of_voice` and `sentiment.score`.
- The dimension writes the same data into `technical/llm_reputation.json` under the keys `branded`, `answers` and `scores`.
- Limitations are added to the manifest:
  - the sample size
  - the model and date
  - no web search
  - entity matching is by domain or name, so aliases may split
  - generated questions reflect the model's own inferred ICP

## Errors

- If one sample or extraction fails, `error` is recorded on that answer, the answer is left out of the scoring counts, and the status becomes `PARTIAL`.
- If question generation fails, or there are no successful unbranded answers, the rank is `null`. The status is `PARTIAL`, and the branded results are still written.
- If the branded question itself fails, the existing behaviour is unchanged.

## Rubric and report

Update `.agents/skills/footprint-analyze/references/llm_reputation.md`:
- Report the rank, mention rate, share of voice and sentiment with their `n`.
- Quote representative answers.
- Name the companies ranked above the target.
- Remove the PASS/WARNING/FAIL verdicts for this dimension.
- Keep `business_impact`.

## Testing (`tests/test_reputation.py`)

The stub LLM returns scripted answers and extractions. The tests cover:
- Leaderboard order, including tie-breaking by average position
- Rank, and `null` when the target is unranked
- Mention rate and share of voice
- Entity keys: matching by domain, and matching by name only
- Sentiment scaling, the branded/unbranded split, and `null` when `n = 0`
- User questions skipping generation, and a generated question naming the target being dropped
- Partial failures being excluded from counts and marking the status PARTIAL
- The CLI flags, and all three files appearing in the manifest

Tests make no network calls.

## Out of scope

- Comparing results across runs over time
- Several models in one run
- Web-search-enabled answers
- Concurrency
- A 0–100 or composite score
