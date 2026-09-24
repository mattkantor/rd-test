# LLM reputation

Source: `technical/llm_reputation.json`:
- `branded`: one model's answer to "what do you know about this company", with its extraction.
- `prompts` and `answers`: unbranded buyer questions, each asked several times, with the companies each answer named.
- `scores`: the leaderboard rank and sentiment computed from those answers, plus `recognized` and `visibility`.
- `profile`: the identity profile built from the crawl and user input (names, cities, phones, categories, official profiles).
- `site_read`: one model's INFERRED read of up to 6 crawled pages: name, category, offerings, cities, service area, phones and who the site sells to (`site_icp`), with `evidence` quotes. A quote with `verified: false` was not found in the captured text; don't rely on it. Its values feed `profile` and, when the user gave none, the buyer questions' ICP and location (`audience` source `site`).
- `icp_check` (only when the user supplied an ICP): the model's INFERRED judgment of whether the site sells to that ICP: `aligned`, `partial` or `misaligned`, with `site_icp` and a reason.
- `branded.identity`: the branded answer's stated facts checked against `profile`. `verdict` is `mismatch` (a fact conflicts: likely a namesake), `confirmed` (an independent fact agrees) or `unconfirmed`. `echoed` facts were in the prompt and prove nothing.
- `audience`: the ICP and location the buyer questions targeted; `source` is `user` (supplied) or `model` (the model's guess).

The model answered without web search. Use the citation shape from [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs use an `R` prefix.

**This dimension reports scores, not verdicts.** Do not assign PASS/WARNING/FAIL. If `status` is `UNKNOWN`, say the LLM request failed and stop.

- **Visibility:** if `scores.visibility` is `not_found`, lead with it: the model did not recognize the company by name and never named it in any buyer answer. That is a result, not a failure: the business needs more exposure before assistants will recommend it. Do not invent a rank or sentiment for it. `not_recommended` means it was recognized but never named unprompted.
- **Rank:** report `scores.rank` of `scores.of` (e.g. "#3 of 9"), with `mention_rate`, `share_of_voice`, `answers_scored` and the number of questions. If `rank` is null, say the company was not named in any buyer answer.
- **Leaderboard:** name the companies ranked above the target, with their mention counts and average positions. These are the competitors a buyer is steered towards instead.
- **Sentiment:** report `scores.sentiment.score` (−100..+100) with `n`, the branded and unbranded split, and the min–max range. A null score means no answer discussed the company.
- **Evidence:** quote representative answers, both one that names the target and one that doesn't. Never paraphrase a model's answer into a stronger claim. Answers are OBSERVED *model claims*, not facts.
- **Identity:** if `branded.identity.verdict` is `mismatch`, report that the model confuses the company with a different business (name the conflicting facts). This is a finding in its own right: buyers asking about the company by name get told about someone else. `unconfirmed` means recognition rests on facts the prompt supplied; say so rather than calling the company recognized with confidence.
- **ICP fit:** if `icp_check.verdict` is `partial` or `misaligned`, report it as a positioning finding: the website speaks to `site_icp`, not the stated ICP, so buyers in the stated ICP may not see themselves in it, and assistants that learn from the site will describe it that way. Cite verified `site_read.evidence` quotes and the page text itself. It is an INFERRED judgment; say so.
- **Accuracy:** compare the branded answer against the website comprehension pass (identity, offer, ICP, location). Note if the model described the company wrongly or confused it with another.
- **Limits:** the sample size, one model, one date, no web search, and entity matching by domain, profile name and city. Assistants with web search may answer differently.
- **Business angle:** buyers increasingly ask assistants for shortlists. A low rank or low mention rate means the company is missing from those shortlists, and the leaderboard shows who is recommended instead.

Add a `llm_reputation` object `{rank, of, mention_rate, share_of_voice, sentiment, top_competitors, summary, findings}` to `analysis.json` and an **AI reputation** section to `report.md`.
