# Security headers

Source: `technical/security.json` (response headers and HTML captured during the crawl). Use the verdicts and citation shape from [analysis-rubric.md](analysis-rubric.md), and give every finding a `business_impact` per [business-impact.md](business-impact.md). Finding IDs use an `S` prefix.

- `PASS`: HTTPS everywhere, and HSTS, CSP, X-Content-Type-Options, Referrer-Policy and frame protection (X-Frame-Options or CSP `frame-ancestors`) are present on core pages.
- `WARNING`: individual headers are missing (name them and give page counts from `missing_summary`); cookies without `Secure`/`HttpOnly`/`SameSite`; `server` or `x-powered-by` headers that reveal software versions.
- `FAIL`: pages served over plain HTTP, or `http://` scripts or images on HTTPS pages (mixed content).
- **Limit:** this reads headers only. It is not a penetration test, and TLS configuration, CMS/plugin versions and vulnerabilities are `UNKNOWN`. Never call a site "secure".
- **Business angle:** larger buyers run vendor security reviews, and browsers warn on mixed content. Missing headers are cheap to fix and read as neglect to technical buyers.

Add a `security` object `{verdict, summary, findings}` to `analysis.json` and a **Security** section to `report.md`.
