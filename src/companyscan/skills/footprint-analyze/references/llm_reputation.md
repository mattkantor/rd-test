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
