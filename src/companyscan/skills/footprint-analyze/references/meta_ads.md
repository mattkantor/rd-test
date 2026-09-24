# Meta Ad Library

Source: `technical/meta_ads.json`, the result of an Ad Library API keyword search for the brand name in `countries`. Use the verdicts and citation shape from [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs use an `A` prefix.

- `status: UNKNOWN` (no token, API error): report the section as `UNKNOWN` and quote the reason. Don't infer "no ads".
- Keyword search can match other advertisers. Only attribute ads whose `page_name` clearly is the company, and list excluded page names.
- The API returns every ad type only for EU/UK delivery. For other countries, an empty result means "no political/issue ads found", **not** "no ads". Mark commercial advertising `UNKNOWN` and recommend a manual check of the Ad Library website.
- Where ads are observed: activity dates (running now? how long?), platforms, and whether the ad copy matches the site's offer, ICP and claims. Compare ad claims to the website (price, contract terms, location) and flag contradictions as `WARNING` or `FAIL`, citing both sources.
- **Business angle:** paid traffic that lands on a page contradicting the ad wastes spend and trust. Ads that stopped long ago can signal a channel that was abandoned.

Add a `meta_ads` object `{verdict, summary, ads_attributed, findings}` to `analysis.json` and a **Paid social (Meta)** section to `report.md`.
