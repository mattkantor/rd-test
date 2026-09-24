# Run dashboard: design

Date: 2026-09-23 · Status: approved in chat, awaiting spec review · Depends on: `2026-09-23-reputation-ranking-design.md`

## Goal

One HTML page per crawl bundle in the local `companyscan serve` UI that shows everything the run captured: status, pages, technical reports, accessibility, the optional dimensions (including the AI reputation rank and sentiment), social and identity data, the report, and coverage limits. Headline cards sit at the top, with a collapsible section per area below them.

## Decisions

| Topic | Decision |
|---|---|
| Scope | The whole crawl bundle, not only the reputation data |
| Delivery | A new route in the existing FastAPI app. It reads the bundle from disk on each request. No static export. |
| Layout | Summary cards first, then native `<details>` sections. No JavaScript. |
| Pages sorting | Server-side, using `?sort=<column>` links (and `&desc=1`) |
| Dependencies | None new. It uses Jinja templates and CSS. |

## Route

- `GET /run/{dir}` → `dashboard.html`. `dir` must resolve inside `root` and contain `manifest.json`, otherwise the response is 404.
- `/report` already makes this check inline; extract it into a helper, `bundle_path(root, dir) -> Path | None`, and use it in both places.
- The manifest must also be a crawl bundle: it has `counts`, as in `sites()`. A standalone `reputation` bundle returns 404.
- Home page: each row gets a **Dashboard** link to `/run/<latest dir name>`.

## Data layer: `src/companyscan/web/dashboard.py`

`load(bundle: Path, sort: str = "id", desc: bool = False) -> dict` builds the whole view model, so the template only lays it out.

- `read(bundle, rel)` returns the parsed JSON, `MISSING` when the file is absent, or `UNREADABLE` on an OSError or ValueError. Sections render "not collected" or "unreadable" for those values.
- `integrity` = `report.analyze.verify(bundle)`. An empty list means intact, otherwise it holds the problem strings. If `verify` itself fails, it is `UNREADABLE`.
- `link(url)` returns the URL only when its scheme is `http` or `https`, and `None` otherwise. The template renders the `href` only when this is not None, always with `rel="noopener noreferrer"` and `target="_blank"`.
- `cards`: a list of `{title, lines: [str], anchor}`, one per area in section order. Areas that weren't collected are left out, except Report, which always shows.

### Sections and their sources

| Section | Source | Content |
|---|---|---|
| Header | `manifest.json` | host, local `created_at`, status, command, counts, config (`max_pages`, `max_depth`, `dimensions`), error count, integrity |
| Report & findings | `latest(bundle,"report.md")`, `latest(bundle,"report.pdf")`, the latest `analysis.json` | links, and findings as rows of `{id, verdict, title}` when `findings` is a list. Otherwise a "report present" link only. There is a "Generate report" button (the existing `/report` POST) when no report exists. |
| Pages | `pages/*.json` | a row per page: id, url (safe link), status, `classification.label`, title, depth, CTA count, `extraction_status`, and links to the page JSON and content `.md`. Sortable by `id`, `status`, `label`, `title` and `depth`. An unknown sort value falls back to `id`. |
| Technical | `technical/{robots,sitemap,crawler-access,indexing,redirects,headers,schema,aeo,measurement,social-preview,llms,feeds}.json` | one sub-block each: key fields plus a table of its list items (bot checks, AEO `issue_summary`, measurement `tools`, social-preview `issue_summary`), with the robots and llms text in `<pre>` |
| Accessibility | `technical/accessibility.json` | automated status, conformance status, pages checked, and a findings table (rule, WCAG criterion, page URL, snippet), plus a link to `accessibility.md` |
| Security | `technical/security.json` | HTTPS, and `missing_summary` as a header/page-count table |
| Fonts | `technical/fonts.json` | distinct families, and a family/page-count table |
| Meta ads | `technical/meta_ads.json` | status, reason, ad count, and a per-page-name count table |
| AI reputation | `technical/llm_reputation.json` | **New shape** (`scores` present): the rank of N, mention rate, share of voice, the sentiment score and its branded/unbranded split with `n`, the leaderboard table (with the target row highlighted), and each buyer question with its sampled answers in a nested `<details>` (raw answer and companies named). **Old shape**: the branded answer and competitors, with "no ranking in this run". **`status: UNKNOWN`**: the error. |
| Social & identity | `social/discovered.json`, `company.json` | the profiles table (platform, safe-linked URL, source) and the company name candidates with their sources |
| Coverage & limits | `urls.json`, `manifest.json` | skipped URLs with reasons, manifest `errors`, and `limitations` |

Every section links to its raw file through the existing `file_url` filter and `/files/`.

## Safety

- All captured content is untrusted. Jinja autoescape stays on, and `|safe` is never used.
- Links from captured data go through `link()`, so only http/https URLs become `href`s.
- The existing localhost-only host check and same-origin protections cover the new route.

## Styling

- `views/templates/dashboard.html` is a standalone template in the same structure as `index.html`, with no template inheritance.
- Card grid, section and table styles are appended to `views/static/app.css`.
- Verdict and status words (PASS/WARNING/FAIL/UNKNOWN/COMPLETE/PARTIAL) get CSS classes by value, so they're coloured.

## Testing (`tests/test_web.py`)

The tests use FastAPI's `TestClient` with a temporary `output/`-style root, following the existing `test_web.py` fixtures. They cover:
- A fully populated bundle renders every section heading and card.
- A bundle without `technical/security.json` renders "not collected" there.
- `/run/../../etc`, an unknown folder and a reputation-only bundle each return 404.
- A page link with a `javascript:` URL is rendered as text, not `href`.
- A new-shape reputation shows `#1 of 2` and the leaderboard. An old-shape one shows "no ranking in this run".
- `?sort=title` orders the rows. `?sort=bogus` falls back to id.
- A modified artifact shows an integrity problem.
- The home page links to `/run/<dir>`.

## Out of scope

- Charts
- A history of past runs for a site
- A static or shareable HTML export
- Rendering report.md as HTML (it is linked, and the PDF exists for reading)
- JavaScript
