# AI slop (Jev)

Source: `technical/jev_copy.json`: TypeSafe Jev's per-page judgment of the page copy (navigation and footer removed), next to the regex `copy_scores.ai_slop` in each page JSON. Use the verdicts and citation shape from [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs continue the `C` prefix from [copy-rubric.md](copy-rubric.md).

- Each page has `ai_slop.score` (Jev's 0–4 rubric level scaled to 0–100, same LOW/MEDIUM/HIGH bands), `confidence` (0–1), `first_hand` (probability the copy has a concrete first-hand detail) and `generic` (probability it could sit on a competitor's site with the name changed). All are `INFERRED`.
- **Read it beside the regex score.** The regex score finds and quotes formula patterns; Jev judges the page as a whole. Where they agree, the call is stronger. Where the regex is high and Jev is low, the page probably has a few formula lines in otherwise human copy: quote the lines, don't call the page slop. Where Jev is high and the regex is low, read the page: generic copy without stock phrases is the newer AI style.
- Ignore judgments with `confidence` under 0.5 unless you confirm them by reading the page. Never quote Jev's score as proof of AI authorship.
- `PASS`: Jev and the regex both LOW on core pages. `WARNING`: a core page is MEDIUM or HIGH on Jev with confidence 0.5+, or `first_hand` is under 0.3 on the home or service pages. `FAIL` is not used: this is a judgment signal, not an observed defect.
- `status: UNKNOWN` with `reason: no_key` means the dimension ran without `JEV_API_KEY`; say so in one line. Pages with `error` weren't judged; name them.
- **Business angle:** copy a buyer could find on any competitor's site gives them no reason to choose this company, and reads as low-effort to the people the company most wants to impress.

Add a `jev_copy` object `{verdict, summary, disagreements, findings}` to `analysis.json`, where `disagreements` lists pages where Jev and the regex score differ by a band or more, and fold the results into the **Copy scores** table in `report.md` as a Jev column.
