# Answer coverage

Source: `technical/answer_coverage.json`. It lists high-intent questions a buyer might ask an AI assistant, written by one model from the site's own offerings (`site_read.offerings`), each judged against up to 3 crawled pages:
- `questions[]`: `question`, `offering`, `intent` (`cost`, `availability`, `suitability`, `comparison`, `process`, `other`), `candidates` (the pages judged), `coverage` (`answered`, `partial`, `missing`; null if the judgment failed, with `error`), `best_url`, `quote` with `verified`, and `gap` (what a page would need to add).
- `summary`: counts per coverage level.
- `questions_from`: the earlier run whose questions were reused (so verdicts compare question by question); null when written fresh. With reused questions there's no site read, so `site_read.offerings` is empty.

Every verdict is INFERRED: one model's reading of the captured text, not proof. A quote with `verified: false` was not found on the page, so don't rely on it and say the answer is unconfirmed. Use the verdicts and citation shape from [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs use a `Q` prefix. If `status` is `UNKNOWN`, say why and stop.

- **Why it matters:** assistants answer buyers from pages that answer the question. When no page on the site answers "what does X cost" or "can you see me Saturday", an assistant cites someone else's page, or answers without naming the business.
- **Verdict:** PASS if most questions are `answered`. WARNING if several are `partial` or `missing`. FAIL if most commercial questions (`cost`, `availability`, `suitability`) are `missing`. Don't average these into a score.
- **Findings:** group the gaps by offering and intent (e.g. "no page gives price ranges for any treatment"). Cite `best_url` and the `gap`. A `partial` with a `best_url` is the cheapest fix: extend that page. A `missing` means a new page, or a section on the offering's page.
- **Evidence:** quote verified `quote`s for answered questions. For missing ones, the evidence is that no crawled page addressed it; note that the crawl may not have reached every page (see `limitations`).
- **Heuristic:** the questions are generated, not taken from search or assistant data. Present them as likely buyer questions, not measured demand.
- **Recommendations:** one per gap group, naming the page to create or extend and what it must state (prices or ranges, hours, who it suits, steps, comparisons). Ask for specifics only the business has, not generic copy.

Add an `answer_coverage` object `{verdict, summary, answered, partial, missing, findings}` to `analysis.json` and an **Answer coverage** section to `report.md`.
