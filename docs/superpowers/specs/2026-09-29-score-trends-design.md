# Score trends on the site dashboard

## Goal

Show how each measurable check moves across a site's runs, so improvement (or slippage) is visible at a glance, and
make the Overview lighter than it is today.

Agreed with the user:
- Store every run's scores; chart each one over time.
- Yes/no facts show current state only, no trend.
- The numbers charted are the **tile metrics** the dashboard already computes from the scan, not the scorecard's 0–100
  area scores (those need a report and shift with LLM verdicts).
- Trends live on the Overview as tiles with a sparkline; the Overview gets shorter, not longer.

## Storage

`Snapshot` (one per crawl, kept after its bundle is deleted) gains `metrics = JSONField(default=dict)`: a flat
`{key: number}` for that run. One migration.

- `sync()` fills `metrics` when it creates a snapshot, alongside `checks`.
- Backfill: `sync()` also fills `metrics` for any existing snapshot whose `metrics` is empty and whose bundle is still on
  disk. Snapshots of deleted bundles stay empty; their runs are gaps, so a chart starts at the oldest surviving bundle.
- A metric the run didn't measure (dimension not run, check UNKNOWN, nothing to count) is absent from the map, never 0.

## One source of truth: `dashboard.metrics(model, raw)`

The numbers each tile shows today move out of `tiles()` into `metrics(model, raw) -> {key: number}`. `tiles()` and
`sync()` both read it, so a stored value always equals what that run's tile showed. `sync()` calls
`dashboard.load(bundle)` to get `model` and `raw`. That's the same cost as opening the dashboard, once per new run.

`METRICS` is a fixed table in `dashboard.py`: `key -> (label, higher_is_better, format)`. `higher_is_better` is `True`,
`False` or `None` (neutral: no ▲/▼ colour).

| key | label | better | from |
|---|---|---|---|
| `pages` | Pages crawled | neutral | manifest counts |
| `a11y_findings` | Accessibility barriers | lower | accessibility `finding_count` |
| `ai_slop` | AI slop (median) | lower | copy-scores median |
| `marketing_bias` | Marketing bias (median) | lower | copy-scores median |
| `analytics_pct` | Pages with analytics | higher | measurement: checked − missing / checked |
| `seo_pct` | Pages passing SEO basics | higher | SEO area on page cards |
| `jsonld_pct` | Pages with JSON-LD | higher | aeo |
| `aeo_issues` | Structured-data issue types | lower | aeo `issue_summary` |
| `social_issues` | Social preview issue types | lower | social-preview `issue_summary` |
| `security_headers` | Security headers present | higher | security, out of `SECURITY_CHECKS` |
| `font_families` | Named font families | lower | fonts |
| `meta_ads` | Meta ads running | neutral | meta_ads `ad_count` (only when shown) |
| `ai_rank` | AI reputation rank | lower | llm_reputation scores |
| `ai_mention_rate` | AI mention rate | higher | llm_reputation scores |
| `ai_sentiment` | AI sentiment | higher | llm_reputation scores |
| `search_rank` / `search_mention_rate` | AI search rank / mention rate | lower / higher | ai_search scores |
| `answered` | Buyer questions answered | higher | answer_coverage summary |
| `practitioner_pages` | Practitioners with own page | higher | practitioners summary |
| `rating` / `reviews` | Google rating / reviews | higher | google_business reviews |

Percentages are stored as 0–100 integers so sparklines share a scale per metric. The Report tile (findings count) is not
trended: it exists only for runs with a report.

## Yes/no facts: current-state row

Not stored as metrics. One compact row under Anomalies: **Analytics**, **Consent tool**, **Ad pixel**, **HTTPS**,
**Google listing found**, each ✓/✗ (or "—" when not checked), from the current run only. The Analytics and Ad pixel
tiles are replaced by this row. Analytics coverage stays trended as `analytics_pct`.

## Trend tiles

Each numeric tile keeps its title, value, sub-line, level and link, and adds:
- **Change since the previous run that has this metric**, e.g. `+3 ▲`, coloured by `higher_is_better` (green better,
  red worse, grey neutral or same). None when there's no earlier value.
- **Sparkline**: inline SVG drawn in the Jinja template from the site's snapshots up to and including this run, oldest
  first, at most the last 12 runs. A run missing the metric is a gap. Each point has a `<title>` with date and value for
  hover. One point: a dot, no line. No JS or chart library.
- Tiles for AI metrics carry the note "Model answers vary between runs; look for changes that hold."

Viewing an older run shows history up to that run only.

**Refined during planning:**
- The Analytics tile stays, showing `analytics_pct` as its trended value; its yes/no and consent parts move to the state
  row. Only the Ad pixels tile is removed (its detail becomes the state row's hover text).
- One sparkline per tile, on the tile's primary metric. Secondary metrics (`aeo_issues`, `ai_mention_rate`,
  `ai_sentiment`, `search_mention_rate`, `reviews`) are stored so history isn't lost; their change shows in the Changes tab.
- AI search, Answer coverage, Practitioners and Google rating get a tile, each only when that check ran.
- The AI noise note is one line under the tile grid, not repeated on each tile.

## Page structure

Overview becomes: Anomalies → current-state row → trend tiles → findings (unchanged).
The **Since last run** panel (question-by-question diffs) moves out of Overview into a new **Changes** tab, unchanged in
content.

## Data flow

`views.render_run` passes the site's snapshots (`name, created_at, metrics`, oldest first, up to this run) to the
template; a small `dashboard.trends(snapshots, current)` builds `{key: {"points": [...], "delta": n, "trend": ...}}`,
which the tile loop reads. `dashboard.py` stays Django-free: it takes plain tuples, as `since_last` already does.
Rendered text (labels, dates) is escaped as today.

## Testing

In `tests/test_web.py`, with the existing loopback fixture:
- `sync()` stores `metrics` on a new snapshot, and backfills an existing snapshot with empty `metrics` when its bundle
  exists.
- A metric absent from a run is absent from `metrics`, not 0.
- `trends()` gives the right delta and trend colour for a higher-is-better and a lower-is-better metric, and a gap for a
  missing run.
- The site page renders a sparkline, the current-state row, and a Changes tab; the Overview no longer contains the
  Since last run table.

## Out of scope

Full-size per-metric charts, scorecard area-score trends, cross-site comparison, trending report findings. Add a large
chart only if sparklines prove too small to read.

## Docs

README "Tracking over time" gains a paragraph on stored metrics and trend tiles; the Web UI section notes the
current-state row and the Changes tab.
