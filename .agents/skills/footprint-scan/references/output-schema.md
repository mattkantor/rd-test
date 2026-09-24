# Output schema v1.0

Every operation writes a new directory, default `output/<host>/`. JSON is UTF-8. Relative artifact paths resolve against the directory containing `manifest.json`. Schema version is `1.0`; consumers should reject unsupported major versions. Retrieval timestamps use UTC ISO 8601. Missing/null information means unknown, not false.

## Manifest

`manifest.json` contains `schema_version`, `command`, `input_url`, `created_at`, effective `config`, `status`, `counts`, `errors`, `artifacts`, and `limitations`.

Each artifact has `path`, `media_type`, `bytes`, and `sha256`. The manifest lists all generated evidence artifacts but does not hash itself. Do not assume unlisted files belong to the scan. Reject paths escaping the bundle root when consuming artifacts. Verify hashes before analysis; disclose changes or missing files.

`COMPLETE` means the bounded operation finished, not exhaustive public coverage. `PARTIAL` means collection errors, skipped URLs/limits, truncation, or no captured pages. HTTP errors remain recorded. Exit codes: 0 complete; 1 partial scan or batch with incomplete rows; 2 command/output error. `--json` emits one JSON result to stdout, including the manifest path and counts; scan evidence itself resides in files.

## Files

| Path | Contents |
| --- | --- |
| `company.json` | `names`, `structured_entities`, `identity_status`; sourced identity candidates, not resolved company facts |
| `urls.json` | `sitemap_urls`, `retrieved`, `skipped` with reasons, sourced HTML `links` |
| `discovery.json` | Input URL/origin, robots capture, sitemap documents, sitemap URLs, HTML canonical/feed/schema signals |
| `pages/0001.json` | Retrieval metadata and HTML extraction below, plus `copy_scores` on extracted non-duplicate pages: `words_scored`, `chrome_lines_removed`, `lexicon_version`, and `ai_slop`/`marketing_bias` each as `{score 0-100 or null, level LOW/MEDIUM/HIGH/UNKNOWN, top_signals, signals: {name: {count, subscore, examples}}, kind: INFERRED}` |
| `content/homepage.md` | Readable extracted text with URL/time; repeated classes use `service-0003.md` etc. |
| `technical/robots.json` | Response metadata, raw policy text, policy status |
| `technical/sitemap.json` | Bounded sitemap documents and discovered locations, parse errors, skipped documents, limits |
| `technical/crawler-access.json` | Per-agent/per-URL robots policy checks; actual bot access remains untested |
| `technical/schema.json` | Parsed JSON-LD documents, types, syntax errors and per-page `issues` from property/reference checks |
| `technical/redirects.json` | Observed redirect chains and errors |
| `technical/headers.json` | Response status and headers |
| `technical/indexing.json` | Canonicals, robots meta, X-Robots-Tag, noindex observations, HTML extraction heuristic |
| `technical/llms.json` | llms.txt response/text, or unknown with reason |
| `technical/feeds.json` | Discovered RSS/Atom URLs; feed contents not fetched |
| `technical/copy-scores.json` | Site summary of per-page copy scores: `pages_scored`, `pages_unscored`, `ai_slop` and `marketing_bias` (median, mean, HIGH/MEDIUM counts, `by_page_type`, `top_pages`), `skeleton_openings`, `chrome_lines`, `lexicon_version` |
| `technical/measurement.json` | Analytics, tag manager, ad pixel, session recording, marketing automation and consent tools found in server HTML, with IDs and per-page coverage. Runtime-injected tags are not observed |
| `technical/aeo.json` | Site-wide structured-data summary: types, issue counts (missing required or recommended properties, incomplete or invisible FAQs, unresolved or conflicting `@id`), and entities grouped by `@id` across pages |
| `technical/social-preview.json` | Per-page `og:`/`twitter:`/`fb:` tags, icons and preview issues (missing tags, non-absolute image, missing dimensions, og:url vs canonical, truncation risk). Images are not fetched |
| `social/discovered.json` | Profile candidates, evidence, confidence, verification/retrieval status; search status |

Retrieval metadata: `url`, `final_url`, `status` (HTTP integer or null), `headers`, `redirects`, `error`, `retrieved_at`, `truncated`.

HTML page fields: `id`, `depth`, `extraction_status`, `title`, `meta_description`, `canonical_url`, `headings`, `visible_text`, `links`, `images`, `json_ld`, `open_graph`, `author`, `dates`, `times`, `addresses`, `telephone_numbers`, `emails`, `ctas`, `faqs`, `testimonials`, `quotation_candidates`, `robots_meta`, `social_meta`, `icons`, `script_sources`, `measurement`, `feeds`, `classification`, `limitations`, optional `content_path` and `duplicate_of`. Failed/non-HTML pages omit unavailable extraction fields.

Classification shape: `{label, kind: "INFERRED", confidence, evidence}`. Labels: homepage, about, service, product, pricing, location, person, case-study, testimonial, article, resource, contact, careers, legal, other. Confidence is a transparent heuristic strength, not calibrated probability. Quote candidates are not automatically testimonials. FAQs/reviews are extracted from JSON-LD in V1.

Social candidate shape:

```json
{
  "network": "linkedin",
  "url": "https://www.linkedin.com/company/example",
  "official_confidence": 0.9,
  "verification_status": "unverified",
  "status": "DISCOVERED_NOT_COLLECTED",
  "profile": {"name": null, "description": null, "location": null},
  "recent_content": [],
  "evidence": [{"source": "https://example.com/", "method": "JSON-LD sameAs", "kind": "OBSERVED"}],
  "retrieval": {"method": null, "retrieved_at": null}
}
```

Successful optional HTML capture adds `captured_page` and changes status to `PUBLIC_HTML_CAPTURED_UNVERIFIED`. It does not assert that a 200 response is a usable profile: login/challenge pages require review. V1 does not extract recent posts or verify ownership automatically. Scores are heuristic link strength: sameAs .9, HTML link .75, OpenGraph .6, user-supplied .5.

Batch output defaults to `output/<csv-filename-without-extension>/` unless `--output` is supplied, and has `batch.json` with `schema_version` and `rows`. Each row has CSV line number, domain, status, and a manifest/counts or error. Row directories are prefixed by row index to support repeated domains. Input contact/phone columns are not copied into evidence bundles.

## Accessibility extension

New captures add `pages/*.json.accessibility` with engine/version, `checks` and `findings`. `technical/accessibility.json` aggregates findings, checked pages, excluded captures and skipped URLs. `technical/accessibility.md` is the readable report; both are manifest-listed. Findings include rule ID, WARNING severity, INFERRED kind, confidence, source URL/artifact/time, HTML line/column/snippet, WCAG criterion/level/reference, and recommendation.

Target: WCAG 2.2 Level AA; implementation: selected static HTML checks of Level A features. This does not evaluate all A/AA requirements. `automated_status` is PASS, WARNING or UNKNOWN, scoped strictly to those checks. `conformance_status` is always UNKNOWN and `manual_review_required` is true. Legacy bundles lacking accessibility data remain usable but cannot support an accessibility assessment. CLI summaries expose the statuses, pages checked, finding count and report path; exit codes still concern collection, not accessibility verdicts.
