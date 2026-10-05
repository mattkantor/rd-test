# Current features (as of 2026-10-05)

What the product does today, from a full read of the code, README, docs and tests. Written as the baseline for a
roadmap: every item below exists and is covered by tests unless marked otherwise. Gaps and limits are at the end.

**One line:** `companyscan` crawls a public company website into a checksummed evidence bundle, optional checks add
off-site and AI evidence, an LLM report interprets the bundle against fixed rubrics, and the web app turns that into a
customer scorecard, a fix pack and run-over-run tracking. Sold as Obvious Choice Systems ("Find → Trust → Choose").

Health: 248 tests pass, ruff clean, Docker Compose deploy to a single droplet documented and run end to end.

## 1. Evidence capture (CLI, stdlib only, no keys)

| Capability | What it does |
|---|---|
| Discovery | robots.txt and sitemap (index) capture with cycle/size/count bounds; crawler-access policy per AI agent (GPTBot, ClaudeBot, PerplexityBot, Google-Extended and others) |
| Bounded same-origin crawl | `--max-pages`, `--max-depth`, delay, timeout, byte cap; robots respected; login/cart/asset/query URLs excluded; cross-origin redirects recorded, not followed; private destinations blocked unless `--allow-private` |
| Per-page extraction | title, description, canonical, headings, visible text, links, images, JSON-LD, Open Graph, author, dates, addresses, phones, emails, CTAs, FAQs, testimonials, quote candidates, robots meta, icons, scripts, Trustpilot widgets, feeds; duplicate detection; page classification (homepage, service, pricing, person, legal, ... INFERRED with evidence) |
| Readable content | `content/<class>.md` per page with nav/footer "chrome" lines identified |
| Copy scores | Regex-based **AI slop** and **marketing bias** 0–100 per page and site summary (stock phrases, rhythm, template skeleton, contrast frames, unsupported claims, self-focus, pressure, FOMO, authority), each with quoted examples |
| Technical reports (always written) | robots, sitemap, crawler access, redirects, headers, indexing (canonical/noindex), `llms.txt`, feeds, schema (JSON-LD parse + property/`@id` issues), AEO summary, social previews (og/twitter completeness, image, truncation), measurement (analytics, tag manager, ad pixels, session recording, marketing automation, consent tools, with IDs and page coverage), social proof |
| Social proof | Shown (JSON-LD reviews, testimonial section, attributed quotes, review widgets, printed ratings) and asked (review links incl. Google write-review, testimonial and referral asks). PASS/WARNING/FAIL. Trustpilot read from the site only |
| Accessibility | Static HTML checks of selected WCAG 2.2 Level A rules, per-page findings with line/col/snippet, aggregate JSON + Markdown report, manual-review checklist; conformance always UNKNOWN |
| Social and identity | Profile discovery from site links, JSON-LD `sameAs`, OpenGraph with confidence scores; optional public HTML capture (`--collect-social`); company name candidates from JSON-LD; `--known-profile` merge. Ownership never asserted |
| Bundle | Fresh `output/<host>-<timestamp>/`, never overwritten; `manifest.json` with SHA-256 per artifact, config, counts, errors, limitations; `docs/output-schema.md` v1.0 |
| Subcommands | `scan`, `discover`, `crawl`, `technical`, `social`, `accessibility`, `batch` (CSV of domains, per-row dirs, `batch.json`), `reputation`, `pdf`, `fixpack` |
| Contract | `--json` = exactly one JSON object on stdout; exit 0 complete / 1 PARTIAL / 2 bad invocation |
| Agent operation | `CLAUDE.md` tells Claude Code how to run scans and hand bundles to the `footprint-analyze` skill |

## 2. Optional dimensions (`--dimension`, UI checkboxes)

| Name | Collects | Needs |
|---|---|---|
| `security` | Security headers, mixed content, cookie flags from crawl responses | none |
| `fonts` | Declared font families from inline CSS, same-origin stylesheets, Google/Adobe font URLs | none |
| `llm_reputation` | Identity profile → site read → branded question (namesake check: confirmed/unconfirmed/mismatch) → 8 unbranded buyer questions × 3 samples → rank, mention rate, share of voice, sentiment, visibility (recommended / not_recommended / not_found). ~50 calls | `OPENAI_API_KEY` |
| `ai_search` | Same flow with OpenAI web search on; adds cited sources per answer and the most-cited domains for the market | `OPENAI_API_KEY` |
| `citation_gap` | Fetches the 40 most-cited third-party pages from `ai_search` and checks whether each mentions the business (link, domain, name, person). No LLM | none (needs `ai_search` in the run) |
| `answer_coverage` | 12 service-specific buyer questions (cost, availability, fit, comparison, process) judged against up to 3 candidate pages each: answered / partial / missing with verified quote | `OPENAI_API_KEY` |
| `practitioners` | One LLM read of people pages: credentials, education, associations, focus, media; Person JSON-LD matched in Python; own-page check | `OPENAI_API_KEY` |
| `google_business` | Places API (New) search or direct `--place-id`; listing only counted when website or phone matches the site; compares name, phone, website, postcode, street number; category, hours, status, rating, review count, up to 5 reviews | `GOOGLE_PLACES_API_KEY` |
| `meta_ads` | Meta Ad Library keyword search, only when the site has an ad pixel or tag manager; otherwise SKIPPED | `META_ACCESS_TOKEN` |
| `jev_copy` | TypeSafe Jev holistic AI-slop score per page beside the regex score | `JEV_API_KEY` |

Shared machinery: identity profile (`dimensions/identity.py`) built from flags + JSON-LD + tel links + LLM site read,
with verified quotes; plain-Python ranking (`ranking.py`); every LLM call via `llm.chat_model()` with env-driven
`provider:model` strings (report, reputation, search models). Missing key → that check is UNKNOWN, crawl continues.

## 3. Report and interpretation

| Capability | What it does |
|---|---|
| `footprint-analyze` skill | Shipped in the package. Hash verification, fact ledger with OBSERVED / EXTRACTED / INFERRED / UNKNOWN labels, three comprehension passes (web, social, combined), identity/offer/audience/proof evaluation, copy rubric, measurement/AEO/preview rubric, one rubric per dimension, social proof rubric, business-impact translation per finding. Verdicts PASS / WARNING / FAIL / UNKNOWN, no scores |
| Generate report | `report/analyze.py`: verifies hashes, builds a ~150K-token budgeted digest, one JSON-mode LLM call with SKILL.md + rubrics, model has no tools; Python writes `analysis/report.md` + `analysis.json`; dated subdirectory preserves earlier reports |
| Designed PDF | pandoc + headless Chrome; cover with severity counts, verdict scorecard per dimension, top business impacts, comprehension matrix, issue cards, recommendations, AI-reputation bars, coverage limits, full report appendix; styled by `report.css` |
| Customer scorecard PDF | No LLM. Areas scored 0–100 from verdicts, grouped **Find / Trust / Choose / Measure**; "what this is costing you" with LTV × target customers → value at risk and monthly cost; why each area matters; "We'll handle" from recommendations; Get chosen / Stay chosen offer; service name, pitch, CTA from env. Always labelled as estimates |
| Public scorecard page | `/sites/<uuid>`: login-free, unguessable URL showing the latest reported run's scorecard (costing, where to improve, what's working, CTA) |
| Fix pack (.zip / CLI) | No LLM. `START.md` prompt for a coding agent, one task file per area (analytics and consent, security headers, SEO basics, structured data, link previews, accessibility, unanswered buyer questions, slop rewrites, truthful persuasion, practitioner profiles, social proof), `data/*.json`, `OWNER-TODO.md` for facts the owner must supply and off-site work; ordered by the report's cost ranking |

## 4. Web app (Django + Huey, staff-only)

| Capability | What it does |
|---|---|
| Sites list | Enter URL, tick dimensions, **Crawl**; latest run per site with manifest / report / PDF links; per-site progress bar |
| Site profile | Business name, ICP, category, people, aliases, official profiles, city/state/country, LTV, target customers, Google place ID. Blank fingerprint fields pre-filled from the latest crawl's identity profile for confirmation. Passed to every crawl as CLI flags |
| Jobs | Crawl, Report, **Re-crawl + report** (new run with every dimension, then report + PDF) in the Huey worker; one running job per site (DB constraint); live step/progress/count panel polled every 3s; failures surfaced in the UI with the trace in logs |
| Run dashboard | Tabs: Overview (tiles with change-since-last and 12-run sparklines, yes/no state row, anomalies, attention list), Changes since last run, Pages (cards grouped by Content / SEO / AEO / Social / Accessibility / Analytics / Security, sortable), Site-wide, Meta ads, AI reputation, AI search, Answer coverage, Practitioners, Google Business Profile, Social & identity, Coverage & limits. Every section links to its raw JSON; all captured text escaped |
| Site page | Latest run's dashboard plus History of every crawl; older runs marked as older assessments |
| Tracking over time | Question sets stored per site + profile (ICP, location, category) so runs ask the same buyer questions; site read reused until page text/ICP/model changes; place ID remembered; **Write new questions on the next crawl**; snapshots of tracked checks and 22 headline metrics kept after bundles are deleted; per-check diffs (metrics, question-by-question, competitors and cited sites came/went) |
| Index from disk | `Run` rows rebuilt from manifests on page load, so CLI bundles appear automatically; runs dropped when folders go |
| Downloads | Customer scorecard PDF and fix pack zip rebuilt on every download; bundle files served under `/files/` |
| Admin | Sites, runs (Dashboard, Generate report, Re-crawl actions), jobs, question sets |
| Security posture | Staff login + CSRF; Jinja2 templates with escaping; captured text treated as untrusted everywhere; keys never written to bundles |

## 5. Operations

| Capability | What it does |
|---|---|
| Config | Env-driven settings; `.env` loaded by `manage.py`; SQLite locally, Postgres via `DATABASE_URL`; `COMPANYSCAN_OUTPUT` shared folder |
| Logging | `logs/<cli|web|worker>.log` locally, stderr on a server, off in tests; every swallowed error keeps its trace; prompts, answers and keys never logged |
| Deploy | `Dockerfile` (Python, pandoc, Chromium), `docker-compose.yml` (Postgres, web/gunicorn, worker, Caddy HTTPS, nightly pg_dump backup), `deploy/bootstrap.sh`, `update.sh`; `docs/deploy.md` runbook with checklist, troubleshooting and rollback |
| Dev tooling | `Makefile` (install, dev, test, test-core, lint, scan), ruff config, loopback HTTP test fixture, 248 tests |
| Docs | README (authoritative), `docs/output-schema.md`, architecture diagram, `docs/marketing.md` (positioning, offer, outbound), `docs/delivery/` (10-item engagement playbook with exists / generate / manual tags), design specs and plans under `docs/superpowers/` |

## 6. Business layer already encoded

- **Method:** Find → Trust → Choose (+ Measure), mapped area by area in `scorecard.STAGES`.
- **Offer:** $5,000 "Become the Chosen Practice" fix + $500/month "Stay the Chosen Practice"; copy in `scorecard.ONGOING` / `OUTCOME` and env overrides.
- **Acquisition:** batch-scan a prospect list, rank by opportunity, lead with the scorecard (`docs/marketing.md`).
- **Delivery:** 10 delivery items with intake template, per-customer folder layout, 0/30/60/90-day cadence (`docs/delivery/`).

## 7. Known limits (declared V1 boundaries)

- Server HTML only: no JavaScript rendering, so runtime-injected tags, widget-loaded reviews and client-rendered text are unseen.
- Same-origin only; cross-origin redirects stop the crawl; no auth or anti-bot bypass.
- Heuristics (classification, CTAs, copy scores, accessibility, social proof) are signals, never proof.
- `ai_search` is one engine, one date; `google_business` is one listing with at most 5 reviews; no Apple/Bing/Yelp/directory checks; no Google Search or Maps rank tracking; no competitor ratings.
- Social: discovery only, no platform APIs, no recent-post capture, no ownership verification.
- Single-host runtime: SQLite Huey queue and local bundles mean web and worker share one machine.
- No API or MCP server, no deterministic lead scoring, no competitor comparison, no automatic site repair, no multi-tenant isolation.
- Worker killed mid-job leaves a "running" row that is cleared manually in admin.

## 8. Gaps already identified in the repo (candidates for the roadmap)

From `docs/delivery/README.md` build order, ranked by manual hours saved:

1. Service/location page drafts from the bundle (item 05).
2. Citation target list with prefilled listing data (07).
3. Review kit: write-review link, request and response templates (08).
4. Conversion-event verification: GA4 event snippets for found CTAs, checked on re-crawl (02).
5. Profile data sheet and Google listing mismatch fix list (03).
6. CMS paste sheet for non-static sites (04, path B).
7. Customer-facing then-vs-now progress report from two runs (10).
8. Search rank tracking via a SERP API (09).

Plus, implied by the code and docs but not scheduled anywhere: export/import of site profiles between
installations, Redis queue and shared storage to split web from worker, a public API, scheduled monthly re-crawls,
competitor scans side by side, and a non-OpenAI default so the report and `ai_search` aren't tied to one provider.
