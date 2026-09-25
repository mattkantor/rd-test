# AI search

Source: `technical/ai_search.json`. It has the same flow and fields as `technical/llm_reputation.json`, so apply every rule in [llm_reputation.md](llm_reputation.md) with these differences:

- **Web search was on.** The branded and buyer answers come from `model` using its web search tool. They show what a buyer using an assistant with search is told today, not what the model remembers. Questions, extraction and the site read used `extraction_model`. Don't repeat the "no web search" limit. Instead, say the result reflects one engine, one date and the location the engine searched from.
- **Cited sources:** each answer has `sources` (`url`, `title`), which are the pages the engine cited. `scores.sources` ranks cited domains by how many buyer answers cite them (`answers`) and in total (`citations`). `is_target` marks the company's own domain.
  - Report whether the company's own site is cited in any buyer answer, and in how many. A site that is never cited isn't being used as evidence even when it has the answer.
  - List the top third-party domains (directories, review sites, news, associations, competitors' sites). These are the places the engine relies on for this market. Being listed, accurate and reviewed on them is how a business gets into these answers. Treat them as corroboration targets and name them in recommendations.
  - A domain being cited is OBSERVED. Why the engine chose it is not known; don't claim a ranking factor.
- **Compare** with `technical/llm_reputation.json` when both are present: recognized or named with search but not without it (or the reverse). The two use separately generated buyer questions, so compare the verdicts, not the individual questions.

Finding IDs use an `S` prefix. Add an `ai_search` object `{rank, of, mention_rate, share_of_voice, sentiment, top_competitors, top_sources, summary, findings}` to `analysis.json` (`top_sources`: the most-cited domains, as strings) and an **AI search** section to `report.md`.
