# Company Footprint

A deterministic, dependency-free Python CLI that captures public company website evidence. Two skills adapt it for agents: **scan** collects; **analyze** interprets an existing corpus. Scanning requires no LLM or API key.

Requires Python 3.10+.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
companyscan scan https://example.com --json
```

You can also run without installation:

```sh
PYTHONPATH=src python3 -m companyscan scan https://example.com --json
```

## CLI

```sh
companyscan scan https://example.com --max-pages 500 --output ./output/acme --json
companyscan discover https://example.com --output ./output/discovery --json
companyscan crawl https://example.com --max-depth 4 --output ./output/crawl --json
companyscan technical https://example.com --output ./output/technical --json
companyscan social https://example.com --output ./output/profiles --json
companyscan social https://example.com --collect-social --output ./output/profile-captures --json
companyscan batch prospects.csv --domain-column domain --output ./output/scans --json
```

All commands write evidence bundles. `discover` captures one entry page plus bounded sitemaps; other commands crawl to the configured limits and return the selected view in their JSON result. `scan` returns the manifest path, status and counts, keeping stdout small. `--json` produces one JSON object on stdout, including for argument and runtime errors.

Common options: `--max-pages` (50), `--max-depth` (3), `--timeout` (15 seconds per socket operation), `--delay` (0.25 seconds minimum between requests to an origin), `--max-bytes` (2,000,000 per response), `--max-sitemaps` (20), `--max-urls` (10,000 discovery/queue limit), `--company-name`, `--icp` and `--location` (`"City, State, Country"` for a local business; both steer `llm_reputation` buyer questions), repeatable `--known-profile`, `--collect-social`, repeatable `--dimension` (see [Dimensions](#dimensions)), `--fresh-questions` (see [Tracking over time](#tracking-over-time)). Domain-only input defaults to HTTPS. Robots crawl delays are honored when parseable by Python's robots parser.

Output defaults to `output/<host>-<YYYYMMDD-HHMMSS>/` (UTC), so repeat crawls keep their history; batch runs default to `output/<csv-filename-without-extension>/`. Use `--output ./output/<project>` for a named project. Explicit `--output` paths remain supported as supplied. Existing crawls and analyses have been migrated into `output/` under their original folder names. Choose a fresh output directory on reruns: existing evidence is never overwritten. Exit codes: **0** complete bounded operation, **1** usable partial result (errors, omissions or limits), **2** invalid invocation or output failure. A bounded scan is not a claim of exhaustive coverage. Batch processing is sequential and continues after row errors; `batch.json` records every input row. Duplicate domains get separate row directories.

## Evidence bundle

```text
output/example.com/
├── manifest.json          # configuration, coverage, artifact sizes/hashes
├── company.json           # identity candidates with provenance
├── urls.json              # sitemap/link inventory, retrievals, skipped URLs
├── discovery.json
├── pages/0001.json        # response metadata + extraction
├── content/homepage.md   # readable HTML text
├── technical/
│   ├── robots.json
│   ├── sitemap.json
│   ├── crawler-access.json
│   ├── schema.json
│   ├── redirects.json
│   ├── headers.json
│   ├── indexing.json
│   ├── llms.json
│   ├── feeds.json
│   ├── measurement.json   # analytics, pixels, consent tools
│   ├── aeo.json           # structured-data validation for answer engines
│   └── social-preview.json # og:/twitter: preview tags
└── social/discovered.json
```

Every extracted page also gets `copy_scores`: an **AI slop** score (stock phrases, uniform sentence rhythm, openings shared across pages, contrast frames and other structural formulas, vagueness (few concrete numbers), placeholder text) and a **marketing bias** score (unsupported claims, self-focus, one-sidedness, pressure, FOMO, loss aversion, authority). Both run 0–100 (LOW <30, MEDIUM 30–59, HIGH 60+, UNKNOWN under 80 words), with every signal's count and quoted examples. They are deterministic heuristics, not proof of AI authorship or dishonesty; the analysis skill confirms or rejects them. Lines shared by half the pages or more are treated as navigation and footer and aren't scored.

Pages preserve title, description, headings, text, links, image alt text, JSON-LD, OpenGraph, author/date metadata, structured addresses, telephone/email links, heuristic CTAs, structured FAQs/reviews and a sourced page classification. JSON-LD syntax errors retain the offending block. Network/HTTP failures are recorded without aborting the scan. See the [output schema](.agents/skills/footprint-scan/references/output-schema.md).

## Agent workflow

From a harness that discovers repository skills:

```text
$footprint-scan https://example.com
$footprint-analyze output/example.com
```

Other harnesses can read the same `SKILL.md` files and run the CLI. Analysis is an agent workflow, not an LLM hidden in the scanner or an `analyze` CLI command. It writes `analysis/report.md` and `analysis/analysis.json`, using only the captured corpus. It separates observation, extraction, inference and unknowns; cites evidence; and runs website-only, social-only and combined comprehension passes. Findings use PASS / WARNING / FAIL / UNKNOWN, with no aggregate score. A marketing copy pass checks persuasion levers (customer-directed before authority), ICP consistency, human voice and goal direction. Every finding is also translated into business impact: what the company loses (leads, deals, trust, visibility) and how.

Skills:

- [Scan](.agents/skills/footprint-scan/SKILL.md)
- [Analyze](src/companyscan/skills/footprint-analyze/SKILL.md) and [rubric](src/companyscan/skills/footprint-analyze/references/analysis-rubric.md) and [copy rubric](src/companyscan/skills/footprint-analyze/references/copy-rubric.md) and [business impact](src/companyscan/skills/footprint-analyze/references/business-impact.md) and [measurement/AEO/previews](src/companyscan/skills/footprint-analyze/references/measurement-aeo-preview.md)

The analyze skill lives in the package (`src/companyscan/skills/`) so **Generate report** works from an installed copy; `.agents/skills/footprint-analyze` is a symlink to it for harness discovery.

## V1 boundaries

- Public server HTML only: no browser rendering, authentication or anti-bot bypass. CSS visibility is only approximated; extraction retains navigation/footer text for evidence. Sparse text is a warning, not proof that a site requires JavaScript.
- Same-origin crawling. Cross-origin redirects are recorded and stopped, including HTTP-to-HTTPS and www changes. Start with the site's final canonical origin; rerun there after reviewing a recorded redirect.
- Robots rules apply to requests and redirect destinations. Missing robots (404/410) permits crawling; unavailable, forbidden or truncated robots yields UNKNOWN and stops page crawling. This uses the standard-library parser, not a full RFC compliance implementation.
- Login/cart/account paths, non-HTML asset extensions and query-bearing URLs are excluded. Tracking parameters and fragments are normalized away. Depth is link distance; sitemap entries are depth 1.
- Sitemap indexes are traversed with cycle/size/count bounds. External-origin and compressed sitemaps are not collected. RSS/Atom URLs are discovered, not ingested.
- Measurement detection reads server HTML only: tags loaded at runtime (e.g. by Google Tag Manager) are not observed, and presence doesn't prove a tag fires. AEO checks cover common rich-result properties and `@id` consistency, not Google's full validator. Social preview images are not fetched.
- Classifications and CTAs are heuristic. Unstructured testimonials/FAQs are not asserted; blockquotes are quote candidates.
- Social discovery uses website links, JSON-LD sameAs and selected OpenGraph fields. Only the site's own identity counts: a link to a social or publishing profile (LinkedIn, Instagram, Medium, Substack, beehiiv, ...) must be on the start page or on at least a third of crawled pages (header/footer), and names and `sameAs` come only from top-level JSON-LD entities, so a case study's nested `about` client is ignored. No external search, platform API or recent-post adapter is built in. Discovered accounts remain unverified. Optional public HTML captures may be login/challenge screens and require review; social failure never invalidates the website evidence.
- Robots checks describe declared bot policy, not actual bot access, search indexing or AI visibility. `llms.txt` does not prove AI visibility.
- `ai_search` is one engine (OpenAI web search), one date and whatever location that engine searched from. Cited sources are what it chose to cite, not a full list, and not proof of why it ranked anyone.
- `answer_coverage` questions are generated from the site's offerings, not measured search or assistant demand, and its verdicts are one model's judgment of at most 3 pages per question.
- `practitioners` reads only the website: directory, association and media profiles elsewhere are not searched, and `sameAs` links are listed, not visited.
- `google_business` is one Google search and one listing. Google returns at most 5 reviews, chosen by relevance, and hours aren't compared. Apple, Bing, Yelp and directory listings aren't checked.
- Non-public destinations are blocked by default, including redirect targets. `--allow-private` is for trusted local fixtures. This CLI is not a hardened multi-tenant URL-fetch service: DNS validation is not connection-pinned; do not expose it to untrusted remote jobs without egress isolation.
- No deterministic lead-scoring/filtering, competitor comparison, automatic site repair, API, dashboard or MCP server in V1. Batch scanning supplies evidence for those future workflows.

## Web UI

```sh
python -m pip install -e '.[web]'   # Django + Huey; the scanner itself stays dependency-free
python manage.py migrate
python manage.py createsuperuser    # the UI and admin are staff-only
python manage.py runserver          # http://127.0.0.1:8000
python manage.py run_huey           # second terminal: the worker that runs crawls and reports
```

A Django app for staff users: enter a URL, tick dimensions, and **Crawl**. The table lists each site's latest crawl, and **Last crawled** is that bundle's `manifest.json` `created_at`. The bundles on disk stay the evidence: the database holds a `Run` index of them (rebuilt from the manifests whenever the site list or the admin run list loads, so bundles written by the CLI appear automatically), plus `Site` and `Job` rows. **Generate report** verifies the bundle's hashes, builds a digest of the bundle (about 150K tokens: technical reports, page metadata and page text with navigation/footer lines removed, trimmed evenly on large sites and noted in the report), and sends it with the `footprint-analyze` skill and its rubrics to OpenAI in one LangChain call. The model has no tools; Python writes `analysis/report.md` and `analysis/analysis.json`, then renders the PDF. It needs `OPENAI_API_KEY`. The output folder defaults to `./output` where you start the server and worker; set `COMPANYSCAN_OUTPUT` to change it (both processes must share it).

Crawl, report and re-crawl jobs run in the Huey worker, which writes progress to the `Job` row; a database constraint allows one running job per site. If a worker dies mid-job, set that job's state to `error` in the admin to unblock the site. `/admin/` lists sites, runs (with a **Dashboard** link and **Generate report** / **Re-crawl** actions) and jobs.

Configuration is by environment:

| Variable | Local default | Server |
| --- | --- | --- |
| `DATABASE_URL` | unset: SQLite `./db.sqlite3` | `postgres://user:pass@host:5432/db` (Postgres 15+ with Django 6; 14 works on Django 5.2) |
| `DJANGO_DEBUG` | `1` without `DATABASE_URL` | `0` when `DATABASE_URL` is set |
| `DJANGO_SECRET_KEY` | dev key | required |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | your hostname(s), comma-separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | none | `https://your.host` behind a proxy |
| `HUEY_DB` | `./huey.sqlite3` | the queue file; web and worker must share it (one host) |

On a server, run `python manage.py collectstatic` (WhiteNoise serves the files) and serve `companyscan.server.wsgi:application` with any WSGI server.

Each site's **Dashboard** link (`/site/<id>`) is the site page: the dashboard of its latest crawl (the current assessment) plus a **History** table of every crawl, newest first. Older crawls open at `/run/<bundle>`, marked "older assessment" with a link back to the current one. A dashboard shows everything that crawl captured:
- **Cards:** a summary card per area.
- **Since last run** (on the overview, when an earlier run of the site exists): AI reputation, AI search, answer coverage, practitioners and the Google listing, each against the newest earlier run that has that check. Shows the metrics then and now (better, worse or the same), which questions changed, and which competitors and cited sites came and went. See [Tracking over time](#tracking-over-time).
- **Sections:** a collapsible section for the report and findings; pages (sortable by clicking a column heading); the technical reports; accessibility; security, fonts and Meta ads; the AI reputation rank, sentiment and buyer answers, and the same from web search (AI search) with the sites it cited; answer coverage (which buyer questions a page answers); practitioner profiles; the Google listing next to the website, with its reviews; social profiles and identity; and coverage limits.

Every section links to its raw JSON. Missing files show as "not collected", and all captured text is displayed escaped.

**Re-crawl + report** (on each home-page row and on the dashboard) does everything in one job. It crawls the site again from its `input_url` with **every** dimension, whatever the original run used (WCAG accessibility, analytics, AEO, social previews and the other technical reports always run), then writes the report and PDF for the new run. It writes a new timestamped run and keeps the old one, so the site page then shows the new run and the old one moves to History. Expect a few minutes: `llm_reputation` and `ai_search` each make about 50 API calls (8 at a time; `ai_search`'s 25 answers each run web searches), `answer_coverage` about 15, `practitioners` one, and the report is one long call. `google_business` records `UNKNOWN` unless `GOOGLE_PLACES_API_KEY` is set, `meta_ads` unless `META_ACCESS_TOKEN` is set, and `jev_copy` unless `JEV_API_KEY` is set. If the report step fails, the new crawl is still saved and the error says which half failed.

While a crawl, re-crawl or report runs, the site's dashboard shows a status panel: the current step (`step 3 of 8`), a progress bar, counts where the step has them (pages crawled out of the limit, LLM reputation buyer answers out of the total), and the start time. It refreshes every 3 seconds until the job ends, then shows the result and, after a crawl, a **View new run** link. Only the status panel updates (it polls `/run/<bundle>/job`); the rest of the page stays as it is, with a link to reload once the job ends. The home page shows a smaller bar and status line per site the same way (it polls `/site/<id>/job`), including a site whose first crawl is still running. Buttons on a dashboard return to the page they were clicked on (the site page or that run). The report step is one long LLM call, so it shows its step without a count.

### LLM models

Both LLM steps use LangChain `provider:model` strings, read from the environment:

| Variable | Used for | Default |
| --- | --- | --- |
| `COMPANYSCAN_REPORT_MODEL` | **Generate report** (one long call) | `openai:gpt-5` |
| `COMPANYSCAN_REPUTATION_MODEL` | `llm_reputation` and `companyscan reputation` (~50 short calls); the site read, questions and extraction in `ai_search` | `openai:gpt-4o-mini` |
| `COMPANYSCAN_SEARCH_MODEL` | `ai_search` branded and buyer answers (~25 calls with OpenAI's `web_search` tool, so it must be an OpenAI model that supports it) | `openai:gpt-5-mini` |

`OPENAI_API_KEY` must be exported in the environment the CLI or server runs in; `.env` is not loaded automatically. Other providers work with their LangChain package installed (e.g. `anthropic:claude-sonnet-5` with `langchain-anthropic`).

## Designed PDF

```sh
companyscan pdf output/example.com-20260923-140000
```

Renders the newest `analysis/**/report.md` to `report.html` and `report.pdf` beside it. When `analysis.json` sits beside it, the PDF is laid out from that: a cover with severity counts, a verdict scorecard per dimension, the top business impacts, the buyer-comprehension matrix, issue cards (observation, meaning, confidence, evidence), what's working, recommendations, AI-reputation bars, and coverage limits, with `report.md` as the "Full analysis" appendix. Without it, `report.md` alone is printed. pandoc converts the Markdown, `src/companyscan/views/report/report.css` styles both layouts, and headless Chrome prints. PASS/WARNING/FAIL/UNKNOWN and HIGH/MEDIUM/LOW become coloured badges. It needs `pandoc` and Chrome or Chromium (set `CHROME=/path/to/chrome` if it isn't found). To restyle every report, edit `report.css`.

## Dimensions

Optional extra evidence, collected with `--dimension <name>` (repeatable) or the UI checkboxes. Each one is saved as `technical/<name>.json` and hashed in the manifest. The analysis skill applies `references/<name>.md` when the file is present.

| Name | Collects | Needs |
| --- | --- | --- |
| `security` | Security headers, mixed content and cookie flags from the crawl's responses. No extra requests; not a penetration test. | none |
| `fonts` | Declared font families from inline styles, same-origin stylesheets (up to 20, robots-respecting) and Google Fonts URLs. Declared, not rendered. | none |
| `llm_reputation` | The [reputation](#reputation-optional-llm) rank and sentiment, asked of the reputation model with no tools or web search (model knowledge only); about 50 calls, 8 at a time. | `OPENAI_API_KEY` |
| `ai_search` | The same flow as `llm_reputation`, but the branded and buyer answers come from the search model with web search on, so it shows what an assistant with search tells a buyer today. Adds each answer's cited `sources` and `scores.sources`: the domains cited most across buyer answers (your own site marked), which are the sites the engine relies on for that market. About 50 calls. | `OPENAI_API_KEY` |
| `answer_coverage` | Whether the site answers the high-intent questions buyers ask assistants. The reputation model reads the site (the same read as `llm_reputation`), writes 12 service-specific questions from its offerings (cost, availability, who it suits, comparisons, process), picks up to 3 candidate pages for each from the crawl's titles, descriptions and headings, then judges each question against those pages' text (navigation and footer removed): `answered`, `partial` or `missing`, with the closest page, a quote checked against the page, and what's missing. `INFERRED`. About 15 calls. | `OPENAI_API_KEY` |
| `practitioners` | Whether each practitioner a buyer chooses between (dentist, lawyer, advisor) has a substantial, connected profile. One call to the reputation model reads up to 8 people pages (chosen by URL words such as team, doctor and about, plus pages with Person JSON-LD; navigation and footer removed) and lists each practitioner with their credentials, education, associations, focus, experience, media and community involvement, backed by quotes checked against the page. Plain Python then matches Person JSON-LD by name (its properties and `sameAs` links) and decides whether each has their own page (a page shared by several people isn't). `INFERRED`. | `OPENAI_API_KEY` |
| `google_business` | The business's Google Business Profile, from one Places API (New) text search for its name and city (5 results). A result counts as this business only if its website is this domain or its phone is one of the site's, so a namesake is never taken for the listing (`found: false` lists the candidates instead). Compares the listing's name, phone, website, postal code and street number with the site (JSON-LD, `tel:` links and page text), records its category, hours and status, and the rating, review count and up to 5 reviews Google returns (relevance-ordered; reviewer names are not stored). The key is sent as a header and never written to the bundle. | `GOOGLE_PLACES_API_KEY` (Places API (New) enabled) |
| `meta_ads` | Meta Ad Library API keyword search for the brand name. All ad types are returned only for EU/UK delivery; elsewhere only political/issue ads, so US results are mostly `UNKNOWN`. The token is never written to the bundle. | `META_ACCESS_TOKEN`, optional `META_AD_COUNTRIES` (default `US`) |
| `jev_copy` | TypeSafe Jev's holistic AI-slop judgment of each scored page's copy (nav and footer removed): a 0–100 score with confidence, plus whether the copy has first-hand detail and whether it's generic enough to fit a competitor. Shown next to the regex score. One request per page, 8 at a time; about $0.00005 per page. `INFERRED`; the key is never written to the bundle. | `JEV_API_KEY`, optional `JEV_MODEL` (default `jev-latest`) |

To add a dimension:
1. Add `src/companyscan/dimensions/<name>.py` with `collect(client, discovery, pages, brand) -> dict`.
2. Register it in `DIMENSIONS` in `dimensions/__init__.py`.
3. Add `src/companyscan/skills/footprint-analyze/references/<name>.md` and list it in step 7b of that skill.

## Tracking over time

Runs of the same site are meant to be compared, e.g. monthly. So `llm_reputation`, `ai_search` and `answer_coverage` **reuse the questions** of the newest earlier run in the same output folder that has that check and was asked for the same `--icp` and `--location`. Each records the run it took them from in `questions_from`, and reused buyer questions have `source: previous`. `answer_coverage` then skips its site read. A first run, a changed ICP or location, or `--fresh-questions` writes new ones. The UI's crawl and re-crawl do the same, since their runs share `COMPANYSCAN_OUTPUT`.

The dashboard's **Since last run** panel compares each check with the newest earlier run that has it. Question-by-question rows appear only for questions asked both times. Model answers vary between runs even with the same questions, so small moves are noise: look for changes that hold over several runs.

## Reputation (optional LLM)

Ask an LLM how it ranks and describes a company. This command is an optional extra; the `llm_reputation` [dimension](#dimensions) runs the same flow with the reputation model below.

```sh
python -m pip install -e '.[llm]'
OPENAI_API_KEY=... companyscan reputation https://example.com --json
companyscan reputation example.com --company-name "Example Co" --prompts-file buyer-questions.txt --samples 5
companyscan reputation joespizza.com --company-name "Joe's Pizza" --icp "families ordering takeout" --location "Austin, TX, USA"
```

In the web UI, set a Site's business name, ICP and (for a local business only) city, state and country with **Edit profile** on the site page (or in `/admin/`). A site's URL is set when it is first crawled and can't be edited; crawls pass them as `--company-name`, `--icp` and `--location`.

In the `llm_reputation` dimension it first **reads the site**, since the model can't browse it: one call sends the text of up to 6 crawled pages (homepage, about, services, products, pricing, locations, contact, case studies first; 4,000 characters each) and gets back the business's name, category, offerings, cities, service area, phones and who the site sells to, with supporting quotes. Each quote is checked against the captured text and marked `verified`. When the Site has an ICP, the same call judges whether the site sells to it (`icp_check`: `aligned`, `partial` or `misaligned`, INFERRED). Without a user ICP or location, the buyer questions use the site's instead of the model's guess.

It runs in three steps, after building an **identity profile** of the company: its names (`--company-name` plus JSON-LD `name`, `alternateName` and `legalName`), cities (`--location` plus JSON-LD `addressLocality`), phone numbers (JSON-LD and `tel:` links), business categories (specific JSON-LD types such as `Dentist`) and official profiles (JSON-LD `sameAs` and linked social profiles), plus what the site read found, which fills in sites without structured data. The `llm_reputation` dimension builds it from the crawl; the standalone command has only the flags.

1. **Branded question:** asks what the model knows about the company (with `--location` if given, to pick out a local business; the model is told to say so if it doesn't know it), and extracts the inferred ICP, location, competitors, a sentiment rating, and the website, city, phone and category the answer states. Those facts are checked against the profile: any conflict (another city, website or phone) marks the answer `mismatch`, a namesake, so it counts neither as recognition nor as sentiment. A fact that agrees makes it `confirmed`, unless the prompt supplied that fact (the website, and the city when `--location` is given), since the model may just repeat it. Otherwise it is `unconfirmed`.
2. **Buyer questions:** unbranded questions that don't name the company. By default the model writes them from `--icp` and `--location`, falling back to the ICP and location it inferred (`--num-prompts`, default 8). `--prompt` (repeatable) or `--prompts-file` (one per line, `#` comments allowed) replace the generated set.
3. **Scoring:** each buyer question is asked `--samples` times (default 3), and every answer is extracted into the companies it names, in order, with the website and city it gives for each. A mention is the company when its website is the site's domain, or, with no website, when its name matches a profile name and it isn't placed in a different city.

Scoring is plain Python:
- **Rank:** a leaderboard across all answers, sorted by mentions, then by average list position. You get the company's rank (`#3 of 9`), mention rate and share of voice.
- **Sentiment:** a score from −100 to +100, averaged over the answers that mention the company and split into branded and unbranded.
- **Visibility:** `recommended` (named in buyer answers), `not_recommended` (known by name but never named), or `not_found` (not recognized by name and never named). `not_found` is a result, not an error: the business needs more exposure before assistants recommend it.

There is no pass/fail.

`--model` takes any LangChain `provider:model` string (default: `COMPANYSCAN_REPUTATION_MODEL`, else `openai:gpt-4o-mini`; e.g. `anthropic:claude-sonnet-5` with `langchain-anthropic`). Output goes to `output/<host>-reputation/`:
- `reputation/reputation.json`: the branded answer, its `identity` check and the `profile`
- `reputation/answers.json`: the target `audience` (ICP and location, each marked `user` or `model`), every question, raw answer and extraction
- `reputation/scores.json`: the rank, leaderboard and sentiment

These scores come from a small sample of one model on one date, with no web search, so treat them as indicators. If a sample fails, it is recorded and left out of the counts, and the run is marked `PARTIAL`. The dimension makes about 50 calls with the defaults.

## Code layout

```text
src/companyscan/
├── cli.py, models.py        # entry point; shared config and records
├── scan/                    # deterministic collection: crawler, discovery, extract, schema,
│                            #   technical, measurement, accessibility, social, artifacts (bundle writer)
├── dimensions/              # optional evidence: security, fonts, reputation, meta_ads, jev_copy (+ DIMENSIONS registry)
├── llm.py                   # LangChain chat models; REPORT_MODEL / REPUTATION_MODEL from env
├── report/                  # analyze.py (hash check, digest, one LLM call), pdf.py (pandoc + Chrome)
├── server/                  # Django project: settings.py (env-driven), urls.py, wsgi.py
├── web/                     # Django app: models (Site, Run, Job), views, admin, tasks.py (Huey jobs), dashboard.py
└── views/
    ├── templates/index.html # UI markup (Jinja2)
    ├── static/app.css       # UI styles
    └── report/report.css    # PDF design
```

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Web UI tests run only under Django (plain `unittest` skips them): `.venv/bin/python manage.py test tests --top-level-directory tests` after `pip install -e '.[web]'` runs the whole suite.

Tests use a loopback HTTP fixture, never live social platforms. They verify artifact hashes, crawl/byte/depth bounds, sitemap-index cycles, robots policy (including redirect destinations), extraction, social attribution, private-target blocking, output preservation, and batch continuation.

## Check accessibility

Use this first-pass audit to identify potential accessibility barriers in captured HTML and prepare a manual review against the Web Content Accessibility Guidelines (WCAG) 2.2 Level AA. You don't need a browser installation or extra packages.

Run a bounded accessibility scan into a fresh project folder:

```sh
companyscan accessibility https://example.com \
  --max-pages 50 --output ./output/example-accessibility --json
```

Regular `scan`, `crawl`, `technical`, and batch operations also include these checks. Existing bundles remain unchanged; run a fresh scan to capture accessibility evidence.

Open `output/example-accessibility/technical/accessibility.md` for the readable report. Use `technical/accessibility.json` for automation. Both files appear in the checksummed manifest. Page records include an `accessibility` field with rule results and source HTML snippets.

The checks look for missing document titles and language attributes, image alternatives, associated control labels, and names for buttons, links, and frames. Findings include the source URL, capture timestamp, page artifact, HTML line/column, related WCAG criterion, and suggested remediation. Findings are warnings that need confirmation in the rendered page; this is a custom static checker, not axe-core or a browser accessibility audit.

The JSON result includes an `accessibility` summary. Interpret the statuses as follows:

| Field | Value | Meaning |
| --- | --- | --- |
| `automated_status` | `WARNING` | These checks found potential barriers. |
| `automated_status` | `PASS` | These limited checks found no barriers on the checked pages. |
| `automated_status` | `UNKNOWN` | No usable accessibility captures were available. |
| `conformance_status` | `UNKNOWN` | Full WCAG conformance has not been established. |
| `manual_review_required` | `true` | Browser and human evaluation are still needed. |

Exit codes continue to describe collection success or failure; accessibility warnings do not change them. Inspect `accessibility.automated_status` and `finding_count` to filter batch prospects. A completed scan or automated PASS is not a compliance certificate.

Review `pages_excluded` and `urls_skipped` before interpreting the result. Failed, legacy, duplicate-canonical, and truncated page captures are excluded. The scanner excludes login/cart/account paths, so it cannot evaluate complete journeys such as checkout. Keyboard access, focus, computed contrast, reflow, screen-reader behavior, dynamic widgets, custom ARIA controls, media alternatives, and complete user journeys require additional evaluation. The report includes a starter checklist; it does not cover every A/AA criterion.

For the full requirements and evaluation process, see [WCAG 2.2](https://www.w3.org/TR/WCAG22/) and [W3C conformance evaluation guidance](https://www.w3.org/WAI/test-evaluate/conformance/).
