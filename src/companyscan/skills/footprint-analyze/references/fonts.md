# Font consistency

Source: `technical/fonts.json`: declared font families per page, from inline styles, same-origin stylesheets and Google Fonts URLs. Use the verdicts and citation shape from [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs use a `T` prefix.

- Ignore generic families (`sans-serif`, `serif`, `monospace`, `system-ui`, `inherit`, `-apple-system`, `BlinkMacSystemFont`) and CSS variables (`var(--…)`) when counting brand fonts. Treat obvious fallback stacks as one choice.
- `PASS`: one or two brand families (for example a heading face and a body face) are used across the site.
- `WARNING`: three or more brand families; families that appear on only a few pages (name the pages, since they are often legacy templates, landing-page builders or embedded widgets); icon fonts counted as brand fonts; Adobe kits whose contents are `UNKNOWN`.
- `FAIL`: core pages use different primary families from each other.
- **Limit:** these are *declared* fonts, not rendered ones. The browser may never use a declared family, and JS-injected styles are missing. Recommend a visual check before acting.
- **Business angle:** inconsistent type makes pages look like they come from different companies, which weakens brand recognition and trust. It also usually reveals unmanaged templates in the CMS.

Add a `fonts` object `{verdict, summary, families, findings}` to `analysis.json` and a **Typography** section to `report.md`.
