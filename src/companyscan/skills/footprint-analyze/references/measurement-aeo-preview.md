# Measurement, AEO structured data and social previews

Three checks on the machinery behind the site. Use the same verdicts and citation shape as [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs use an `M` prefix.

Sources: `technical/measurement.json`, `technical/aeo.json`, `technical/schema.json`, `technical/social-preview.json`, and the per-page `measurement`, `social_meta`, `icons` and `json_ld.issues` fields.

## 1. Measurement: can the business see its visitors?

- `PASS`: an analytics tool (GA4, Plausible, Matomo and similar) or a tag manager is present on every core page and on most other pages. Name the tools and their IDs.
- `WARNING`: measurement is present only on some pages (list the gaps); only a tag manager is found, so what it loads is `UNKNOWN`; more than one ID for the same tool (split data); retired Universal Analytics only; ad pixels or session recording with no consent tool detected.
- `FAIL`: no analytics, tag manager or marketing-automation tracking anywhere in server HTML, across adequate coverage.
- **Conversion tracking:** note whether the main CTA leaves the site (for example to a booking tool). Clicks and bookings on another domain are invisible unless that tool is connected; mark that `UNKNOWN`, not `FAIL`.
- **Consent:** where ad pixels or session recording are present, note whether a consent tool was detected. Describe this as a privacy-compliance risk to review, not a legal conclusion.
- **Limit:** detection reads server HTML. Tags added at runtime can exist without being observed, so absence is "not observed in HTML". Recommend checking in a browser before acting on a `FAIL`.

## 2. AEO structured data: can answer engines understand and cite the company?

AEO (answer engine optimisation) depends on consistent, valid structured data that identifies the entity, what it offers, and question-and-answer content.
- **Syntax:** any JSON-LD syntax error is a `FAIL` for that page.
- **Entity:** there should be one `Organization` (or `LocalBusiness`) with a stable `@id`, the same `name` everywhere, `url`, `logo`, and `sameAs` links to the official social profiles. Conflicting names for one `@id`, or the business typed as a `Person`, is a `FAIL`. A missing `sameAs` is a `WARNING`.
- **Required properties** (per `aeo.json` issue summary): missing required properties on types used site-wide is a `FAIL`; missing recommended properties is a `WARNING`. A `LocalBusiness` without an `address` is a `FAIL` for local rich results.
- **Content types:** articles should carry `Article`/`BlogPosting` with `headline`, `author` and `datePublished`; the author should ideally be a `Person` with a `url`. FAQ content should use `FAQPage`, and its questions must be visible on the page (`faq_not_visible` is a `WARNING`). Services should name a `provider` that resolves to the organisation.
- **References:** unresolved `@id` references are a `WARNING`.
- Say plainly that this is not Google's Rich Results Test, and that valid schema doesn't guarantee rich results or AI citations.

## 3. Social previews: does a shared link look good?

Check the homepage and core pages first, then site-wide patterns.
- `PASS`: `og:title`, `og:description`, `og:image` (an absolute https URL, with width and height), `og:url` matching the canonical, `og:type`, and `twitter:card` (`summary_large_image` for big images) are all present.
- `WARNING`: missing dimensions, missing `twitter:card`, the same generic image on every page, `og:url` that doesn't match the canonical, or text likely to truncate (title over roughly 90 characters, description over roughly 200).
- `FAIL`: missing `og:title` or `og:image` on core pages, or an image URL that isn't absolute https.
- Image reachability is `UNKNOWN`, because the scanner doesn't fetch images.
- **Business angle:** links to the site get shared in LinkedIn posts, DMs and the company's own cold emails. A blank or wrong preview lowers clicks from every share.

## Output

Add to `analysis.json` a `technical_marketing` object: `{measurement, aeo, social_preview, findings, recommendations}`. Each of the first three holds `{verdict, summary, evidence}`. Add a **Measurement, AEO and social previews** section to `report.md` with the three verdicts, the key evidence, and findings `M1…`.
