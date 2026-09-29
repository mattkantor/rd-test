# Score Trends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store each run's headline numbers and show them on the dashboard's Overview as tiles with a change arrow and a sparkline, with yes/no facts in one current-state row and the "Since last run" diffs moved to a Changes tab.

**Architecture:** `dashboard.metrics(model, raw)` becomes the one place a run's numbers are computed; `tiles()` displays them and `sync()` stores them in a new `Snapshot.metrics` JSON field. `load()` takes the site's earlier `(created_at, metrics)` history from the view and attaches a sparkline (`spark()`) to each tile. Charts are inline SVG from the Jinja template; no JS or chart library.

**Tech Stack:** Python 3.10+ stdlib, Django (web extra), Jinja2 templates, plain CSS.

**Spec:** `docs/superpowers/specs/2026-09-29-score-trends-design.md`

## Global Constraints

- Core scanner stays stdlib-only; this work touches only `web/`, `views/` and tests.
- `dashboard.py` stays Django-free: it receives plain tuples/dicts.
- A metric a run didn't measure is absent from `metrics`, never 0.
- Percentages are stored as 0–100 integers.
- Sparklines cover at most the last 12 runs; a run missing the metric is a gap.
- All captured text is rendered escaped (Jinja autoescape; never `| safe` on captured data).
- Tests use local fixtures only; never hit live sites.
- Run the full suite with `.venv/bin/python manage.py test tests --top-level-directory tests`.

## Deliberate refinements of the spec (decided while planning)

- **Analytics tile stays**, now showing `analytics_pct` (% of pages with analytics) as its trended value; its yes/no and consent parts move to the state row. The **Ad pixels tile** is removed (its detail becomes the state row's hover text).
- **One sparkline per tile**, on the tile's primary metric. Secondary metrics (`aeo_issues`, `ai_mention_rate`, `ai_sentiment`, `search_mention_rate`, `reviews`) are stored so history isn't lost, and their run-to-run change already shows in the Changes tab.
- Four checks without a tile today get one so their trend is visible: **AI search**, **Answer coverage**, **Practitioners**, **Google rating**, each only when that check ran.
- The AI noise note is one line under the tile grid (shown when an AI tile is present), not repeated on each tile.

## Review Focus

1. A snapshot whose bundle was deleted before this change has `metrics == {}` forever: its run must render as a gap, never crash or count as 0. (Task 3 test: history entry `{}`.)
2. Wrong-shaped JSON (strings where numbers belong, booleans, lists) must never reach `metrics` or crash `sync()`: `num()` rejects bools and non-numbers. (Task 1 test.)
3. A metric that is flat across runs (`hi == lo`) must not divide by zero; the line sits mid-height. (Task 3 test.)
4. A tile for a metric this run didn't measure but earlier runs did: no delta, dots only for earlier runs. (Task 3 test: `trend` is computed from `values[-1] is None`.)
5. Rendering an older run from its own `/run/<name>` page must only use history before that run. (Task 4 test.)

---

### Task 1: `metrics()`: one source of truth for a run's numbers

**Files:**
- Modify: `src/companyscan/web/dashboard.py` (add `METRICS`, `seo_counts`, `metrics` after `tile()` ~line 462; use `seo_counts` in `tiles()`; set `model["metrics"]` in `load()`)
- Test: `tests/test_dashboard.py` (`LoadTest`)

**Interfaces:**
- Produces: `METRICS: dict[str, tuple[str, bool | None, Callable]]` (label, higher_is_better, value formatter); `metrics(model, raw) -> dict[str, int | float]`; `load(...)["metrics"]`.

- [ ] **Step 1: Write the failing tests** in `LoadTest` (after `test_header_integrity_report_tiles_and_anomalies`):

```python
    def test_metrics_are_what_the_run_measured(self):
        m = load(self.bundle)
        # No copy-scores, measurement pages_checked, meta_ads, ai_search or listing in the fixture: absent, not 0.
        self.assertEqual(m["metrics"], {"pages": 3, "a11y_findings": 1, "seo_pct": 50, "jsonld_pct": 67, "aeo_issues": 1,
                                        "social_issues": 0, "security_headers": 5, "font_families": 1,
                                        "ai_rank": 1, "ai_mention_rate": 100, "ai_sentiment": 42})

    def test_metrics_ignore_wrong_shaped_values(self):
        write(self.bundle, "technical/accessibility.json", {"finding_count": True, "pages_checked": 3})
        write(self.bundle, "technical/google_business.json", {"status": "OBSERVED", "found": True, "reviews": {"rating": "4.8", "count": 12}})
        m = load(self.bundle)["metrics"]
        self.assertEqual(m["a11y_findings"], 0)  # A bool isn't a count; the tile shows 0 too.
        self.assertNotIn("rating", m)
        self.assertEqual(m["reviews"], 12)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_dashboard.LoadTest -v` (from repo root; `PYTHONPATH=src` if not installed)
Expected: FAIL with `KeyError: 'metrics'`.

- [ ] **Step 3: Implement.** In `dashboard.py`, right after `def tile(...)`:

```python
def pct(v):
    return f"{v}%"


# Each run's headline numbers: key -> (label, higher_is_better, how to show a value). higher_is_better None: neither
# direction is good or bad (the change shows grey). sync() stores these per run for the trend lines.
METRICS = {
    "pages": ("Pages crawled", None, str),
    "a11y_findings": ("Accessibility barriers", False, str),
    "ai_slop": ("AI slop (median)", False, str),
    "marketing_bias": ("Marketing bias (median)", False, str),
    "analytics_pct": ("Pages with analytics", True, pct),
    "seo_pct": ("Pages passing SEO basics", True, pct),
    "jsonld_pct": ("Pages with JSON-LD", True, pct),
    "aeo_issues": ("Structured-data issue types", False, str),
    "social_issues": ("Social preview issue types", False, str),
    "security_headers": ("Security headers present", True, lambda v: f"{v}/{SECURITY_CHECKS}"),
    "font_families": ("Named font families", False, str),
    "meta_ads": ("Meta ads running", None, str),
    "ai_rank": ("AI reputation rank", False, lambda v: f"#{v}"),
    "ai_mention_rate": ("AI mention rate", True, pct),
    "ai_sentiment": ("AI sentiment", True, lambda v: f"{v:+g}"),
    "search_rank": ("AI search rank", False, lambda v: f"#{v}"),
    "search_mention_rate": ("AI search mention rate", True, pct),
    "answered": ("Buyer questions answered", True, str),
    "practitioner_pages": ("Practitioners with their own page", True, str),
    "rating": ("Google rating", True, lambda v: f"{v}★"),
    "reviews": ("Google reviews", True, str),
}


def seo_counts(pages):
    """(pages the SEO checks ran on, pages with an SEO problem), from the page cards."""
    checked = [c for c in pages if any(a["name"] == "SEO" and a["level"] != "neutral" for a in c["areas"])]
    failing = [c for c in checked if any(a["name"] == "SEO" and RANK[a["level"]] < RANK["neutral"] for a in c["areas"])]
    return len(checked), len(failing)


def metrics(model, raw):
    """This run's number for each METRICS key it measured. A key it didn't measure is left out, never 0, so a trend line
    shows a gap rather than a false drop. The tiles show these; sync() stores them."""
    out = {}

    def put(key, value):
        if num(value) is not None:
            out[key] = value

    put("pages", num(as_dict(model["manifest"].get("counts")).get("pages")) or 0)
    t = raw["accessibility"]
    if isinstance(t, dict):
        put("a11y_findings", num(t.get("finding_count")) or 0)
    t = raw["copy-scores"]
    if isinstance(t, dict):
        for key, _ in COPY.values():
            put(key, as_dict(t.get(key)).get("median"))
    t = raw["measurement"]
    if isinstance(t, dict):
        checked, missing = num(t.get("pages_checked")), num(t.get("pages_without_any_measurement_count")) or 0
        if checked:
            put("analytics_pct", meter(checked - missing, checked)["pct"])
    checked, failing = seo_counts(model["pages"])
    if checked:
        put("seo_pct", meter(checked - failing, checked)["pct"])
    t = raw["aeo"]
    if isinstance(t, dict):
        checked = num(t.get("pages_checked"))
        if checked:
            put("jsonld_pct", meter(num(t.get("pages_with_json_ld")) or 0, checked)["pct"])
        put("aeo_issues", len(as_list(t.get("issue_summary"))))
    t = raw["social-preview"]
    if isinstance(t, dict):
        put("social_issues", len(as_list(t.get("issue_summary"))))
    t = raw["security"]
    if isinstance(t, dict):
        put("security_headers", max(SECURITY_CHECKS - len(as_list(t.get("missing_summary"))), 0))
    t = raw["fonts"]
    if isinstance(t, dict):
        put("font_families", len(named_fonts(t)))
    t = raw["meta_ads"] if model["meta_ads"] else None
    if isinstance(t, dict):
        put("meta_ads", t.get("ad_count"))
    for prefix, rep in (("ai", model["reputation"]), ("search", model["ai_search"])):
        s = rep.get("scores")
        if isinstance(s, dict):
            put(f"{prefix}_rank", s.get("rank") or None)  # 0/None: not named, so no rank to chart.
            rate = num(s.get("mention_rate"))
            put(f"{prefix}_mention_rate", round(rate * 100) if rate is not None else None)
            if prefix == "ai":
                put("ai_sentiment", as_dict(s.get("sentiment")).get("score"))
    t = raw["answer_coverage"]
    if isinstance(t, dict) and t.get("status") != "UNKNOWN":
        put("answered", as_dict(t.get("summary")).get("answered"))
    t = raw["practitioners"]
    if isinstance(t, dict) and t.get("status") != "UNKNOWN":
        put("practitioner_pages", as_dict(t.get("summary")).get("with_dedicated_page"))
    t = raw["google_business"]
    if isinstance(t, dict) and t.get("found"):
        reviews = as_dict(t.get("reviews"))
        put("rating", reviews.get("rating"))
        put("reviews", reviews.get("count"))
    return out
```

In `tiles()`, replace the two SEO list comprehensions with `seo_counts` (behaviour unchanged):

```python
    checked, failing = seo_counts(model["pages"])
    if checked:
        out.append(tile("SEO basics", "?sort=seo#pages", checked - failing, f"of {checked} pages pass title, "
                        "description, H1 and canonical checks", "warning" if failing else "good",
                        plural(failing, "page") + " to fix" if failing else "All pass", meter(checked - failing, checked)))
```

In `load()`, before `model["tiles"] = tiles(model, raw)`:

```python
    model["metrics"] = metrics(model, raw)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m unittest tests.test_dashboard -v`
Expected: all PASS (existing tile tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/companyscan/web/dashboard.py tests/test_dashboard.py
git commit -m "Compute each run's headline numbers in one place"
```

---

### Task 2: Store metrics per run in `Snapshot`, with backfill

**Files:**
- Modify: `src/companyscan/web/models.py` (`Snapshot.metrics`, `sync()`, import `load`)
- Create: `src/companyscan/web/migrations/0007_snapshot_metrics.py`
- Test: `tests/test_web.py` (`WebTests`)

**Interfaces:**
- Consumes: `dashboard.load(bundle)["metrics"]` (Task 1).
- Produces: `Snapshot.metrics: dict[str, number]`, filled by `sync()` for new snapshots and for existing empty ones whose bundle exists.

- [ ] **Step 1: Write the failing test.** Add `import shutil` at the top of `tests/test_web.py` and `Snapshot` to the `companyscan.web.models` import. In `WebTests`:

```python
    def test_sync_stores_each_runs_metrics_and_backfills_old_snapshots(self):
        bundle(self.root, "acme-a", "https://acme.test/", "2026-01-01T00:00:00+00:00")
        sync()
        # No check files in this bundle, so only the page count: what wasn't measured is absent, not 0.
        self.assertEqual(Snapshot.objects.get(name="acme-a").metrics, {"pages": 3})
        Snapshot.objects.filter(name="acme-a").update(metrics={})  # A snapshot stored before metrics existed.
        sync()
        self.assertEqual(Snapshot.objects.get(name="acme-a").metrics, {"pages": 3})
        shutil.rmtree(self.root / "acme-a")
        sync()
        self.assertEqual(Snapshot.objects.get(name="acme-a").metrics, {"pages": 3})  # Kept after the bundle is deleted.
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python manage.py test tests.test_web.WebTests.test_sync_stores_each_runs_metrics_and_backfills_old_snapshots --top-level-directory tests`
Expected: FAIL (`AttributeError: 'Snapshot' object has no attribute 'metrics'` or a missing-column error).

- [ ] **Step 3: Implement.** In `models.py`:

```python
from .dashboard import SNAPSHOT, load, snapshot
```

In `Snapshot`, after `checks`:

```python
    metrics = models.JSONField(default=dict)  # dashboard.metrics for the run: its headline numbers, for trend lines.
```

Update the `Snapshot` docstring to: `"""What "Since last run" compares for one crawl (dashboard.snapshot of each tracked check) and its headline numbers for the trend lines, kept after the bundle is deleted."""`

In `sync()`:

```python
    seen, snapped = [], set(Snapshot.objects.values_list("name", flat=True))
    # Snapshots from before metrics were stored; filled in while their bundle still exists. A real run always has
    # "pages", so a filled snapshot is never empty again.
    unmeasured = set(Snapshot.objects.filter(metrics={}).values_list("name", flat=True))
```

and replace the snapshot block at the end of the loop body with:

```python
        if manifest.parent.name not in snapped:
            checks = {name: snapshot(name, load_json(manifest.parent / f"technical/{name}.json")) for name in SNAPSHOT}
            Snapshot.objects.create(site=Site.objects.get(origin=site), name=manifest.parent.name,
                                    created_at=parse_time(data.get("created_at")),
                                    checks={name: data for name, data in checks.items() if data},
                                    metrics=load(manifest.parent)["metrics"])
        elif manifest.parent.name in unmeasured:
            Snapshot.objects.filter(name=manifest.parent.name).update(metrics=load(manifest.parent)["metrics"])
```

Also update the `sync()` docstring's last sentence to: `A new run also gets a Snapshot (tracked checks and headline numbers), which stays after its folder is deleted.`

Generate the migration, then check it matches:

Run: `.venv/bin/python manage.py makemigrations web --name snapshot_metrics`

Expected file `src/companyscan/web/migrations/0007_snapshot_metrics.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0006_customers_per_year'),
    ]

    operations = [
        migrations.AddField(
            model_name='snapshot',
            name='metrics',
            field=models.JSONField(default=dict),
        ),
    ]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python manage.py test tests --top-level-directory tests`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/companyscan/web/models.py src/companyscan/web/migrations/0007_snapshot_metrics.py tests/test_web.py
git commit -m "Store each run's headline numbers so trends survive deleted bundles"
```

---

### Task 3: Sparklines, state row and tile changes in `load()`

**Files:**
- Modify: `src/companyscan/web/dashboard.py` (`tile()` gains `key`; `tiles()` changes; add `spark`, `facts`; `load()` gains `history`)
- Test: `tests/test_dashboard.py` (`LoadTest`, and the existing tile-list assertion)

**Interfaces:**
- Consumes: `METRICS`, `model["metrics"]` (Task 1).
- Produces: `load(bundle, sort="issues", desc=False, earlier=None, history=())` where `history` is `[(created_at_iso_or_None, metrics_dict)]` oldest first, earlier runs only. Each tile dict gains `"key"` (a METRICS key or None) and `"trend"`: `None` or `{"dots": [{"x", "y", "title"}], "lines": [str], "delta": str | None, "arrow": "▲" | "▼" | "", "trend": "better" | "worse" | "same" | None}`. `model["facts"]`: `[(label, True | False | None, href, detail)]`. `model["ai_note"]: bool`.

- [ ] **Step 1: Write the failing tests** in `LoadTest`:

```python
    def test_trend_lines_deltas_and_gaps(self):
        history = [("2026-07-01T00:00:00+00:00", {"seo_pct": 20, "a11y_findings": 0}), ("2026-08-01T00:00:00+00:00", {})]
        trend = {t["title"]: t["trend"] for t in load(self.bundle, history=history)["tiles"]}
        seo = trend["SEO basics"]
        self.assertEqual((seo["delta"], seo["arrow"], seo["trend"]), ("+30", "▲", "better"))
        self.assertEqual([d["title"] for d in seo["dots"]], ["2026-07-01 20%", "2026-09-23 50%"])
        self.assertEqual(seo["lines"], [])  # The August run didn't measure it: a gap, not a line through it.
        a11y = trend["Accessibility (WCAG)"]
        self.assertEqual((a11y["delta"], a11y["arrow"], a11y["trend"]), ("+1", "▲", "worse"))  # More barriers is worse.
        self.assertIsNone(trend["Report"])  # Not trended.
        line = {t["title"]: t["trend"] for t in load(self.bundle, history=history[:1])["tiles"]}["SEO basics"]
        self.assertEqual([len(points.split()) for points in line["lines"]], [2])
        flat = {t["title"]: t["trend"] for t in load(self.bundle, history=[(None, {"seo_pct": 50})])["tiles"]}["SEO basics"]
        self.assertEqual((flat["delta"], flat["trend"], {d["y"] for d in flat["dots"]}), (None, "same", {14.0}))
        self.assertEqual(flat["dots"][0]["title"], "50%")  # No date for that run.
        first = {t["title"]: t["trend"] for t in load(self.bundle)["tiles"]}["SEO basics"]
        self.assertEqual((len(first["dots"]), first["delta"], first["trend"]), (1, None, None))

    def test_metric_missing_this_run_has_no_delta(self):
        trend = {t["title"]: t["trend"] for t in load(self.bundle, history=[(None, {"analytics_pct": 80})])["tiles"]}
        self.assertEqual((len(trend["Analytics"]["dots"]), trend["Analytics"]["delta"]), (1, None))

    def test_state_row_shows_yes_no_facts(self):
        m = load(self.bundle)
        self.assertEqual([(label, value) for label, value, _, _ in m["facts"]],
                         [("Analytics", True), ("Consent tool", False), ("Ad pixel", True), ("HTTPS", True), ("Google listing", None)])
        self.assertEqual(m["facts"][2][3], "Meta Pixel")
        self.assertTrue(m["ai_note"])
```

Update the tile-list assertion in `test_header_integrity_report_tiles_and_anomalies` (Ad pixels tile removed):

```python
        self.assertEqual(list(tiles), ["Pages crawled", "Report", "Accessibility (WCAG)", "Analytics", "SEO basics", "AEO structured data",
                                       "Social previews", "Security headers", "Fonts", "AI reputation"])  # No Meta ads: not collected.
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_dashboard.LoadTest -v`
Expected: FAIL (`TypeError: load() got an unexpected keyword argument 'history'`, tile list mismatch).

- [ ] **Step 3: Implement.** In `dashboard.py`, add the import next to the existing `ads_pixel`/`shows_ads` import (it's already imported from `..scan.measurement`; no change if so).

Change `tile()`:

```python
def tile(title, href, value, sub="", level="neutral", status="", bar=None, key=None):
    """key: the METRICS entry this tile shows, for its trend line (None: not trended)."""
    return {"title": title, "href": href, "value": value, "sub": sub, "level": level, "status": status, "meter": bar, "key": key}
```

In `tiles()`, pass `key=` on existing tiles: `"pages"` (Pages crawled), `"a11y_findings"` (Accessibility), the copy tiles `key=key` (the loop variable from `COPY.items()`), `"seo_pct"`, `"jsonld_pct"`, `"social_issues"`, `"security_headers"`, `"font_families"`, `"meta_ads"`, and `"ai_rank"` on the scored AI reputation tile (the legacy/unknown AI tiles keep `key=None`). Report keeps `key=None`.

Replace the Analytics tile:

```python
    t = raw["measurement"]
    if isinstance(t, dict):
        share = model["metrics"].get("analytics_pct")
        out.append(tile("Analytics", "?sort=analytics#pages", pct(share) if share is not None else "—",
                        "pages with analytics · " + plural(len(as_list(t.get("tools"))), "tool"),
                        "good" if t.get("has_measurement") else "serious", "Measured" if t.get("has_measurement") else "No analytics",
                        meter(share, 100), key="analytics_pct"))
```

Delete the whole `# A yes/no fact, never scored.` Ad pixels tile block (it moves to `facts()`).

Before `return out` in `tiles()`, add the four new tiles:

```python
    v = model["metrics"]
    if isinstance(model["ai_search"].get("scores"), dict):
        rank, rate = v.get("search_rank"), v.get("search_mention_rate")
        out.append(tile("AI search", "#ai_search", f"#{rank}" if rank else "—",
                        f"named in {rate}% of web-search answers" if rate is not None else "not named in web-search answers",
                        "good" if rank == 1 else "warning" if rank else "serious", "", meter(rate, 100), key="search_rank"))
    if "answered" in v:
        total = num(as_dict(as_dict(raw["answer_coverage"]).get("summary")).get("questions"))
        out.append(tile("Answer coverage", "#answers", v["answered"],
                        f"of {plural(total, 'buyer question')} answered on the site" if total else "buyer questions answered on the site",
                        "good" if total and v["answered"] >= total else "warning", "", meter(v["answered"], total), key="answered"))
    if "practitioner_pages" in v:
        people = num(as_dict(as_dict(raw["practitioners"]).get("summary")).get("practitioners")) or 0
        out.append(tile("Practitioners", "#people", v["practitioner_pages"], f"of {plural(people, 'practitioner')} with their own page",
                        "good" if people and v["practitioner_pages"] >= people else "warning" if people else "neutral", "",
                        meter(v["practitioner_pages"], people), key="practitioner_pages"))
    if "rating" in v or "reviews" in v:
        out.append(tile("Google rating", "#listing", METRICS["rating"][2](v["rating"]) if "rating" in v else "—",
                        plural(v.get("reviews") or 0, "review"), key="rating"))
```

Add after `tiles()`:

```python
SPARK_RUNS, SPARK_W, SPARK_H = 12, 120, 28
NOISY = {"ai_rank", "search_rank"}  # Model answers vary run to run even with the same questions.


def spark(history, key):
    """One metric's trend line. history: [(created_at, metrics)], oldest first, ending with this run. None when no run
    measured it. A run without the metric is a gap; a lone point is a dot. delta and trend compare this run with the
    newest earlier run that has the metric."""
    label, higher, fmt = METRICS[key]
    rows = history[-SPARK_RUNS:]
    values = [num(m.get(key)) if isinstance(m, dict) else None for _, m in rows]
    known = [v for v in values if v is not None]
    if not known:
        return None
    lo, hi = min(known), max(known)
    x = lambda i: round(3 + i * (SPARK_W - 6) / max(len(rows) - 1, 1), 1)
    y = lambda v: round(SPARK_H - 3 - (v - lo) / (hi - lo) * (SPARK_H - 6), 1) if hi > lo else SPARK_H / 2
    dots, segments, segment = [], [], []
    for i, ((when, _), v) in enumerate(zip(rows, values)):
        if v is None:
            segments, segment = segments + [segment], []
            continue
        dots.append({"x": x(i), "y": y(v), "title": f"{str(when or '')[:10]} {fmt(v)}".strip()})
        segment.append(f"{x(i)},{y(v)}")
    now = values[-1]
    before = next((v for v in reversed(values[:-1]) if v is not None), None)
    delta = round(now - before, 1) if now is not None and before is not None else None
    return {"dots": dots, "lines": [" ".join(s) for s in segments + [segment] if len(s) > 1],
            "delta": f"{delta:+g}" if delta else None, "arrow": "▲" if delta and delta > 0 else "▼" if delta else "",
            "trend": metric(label, before, now, higher)["trend"]}


def facts(raw):
    """Yes/no facts for the current-state row: (label, True/False/None when not checked, href, hover detail). This run
    only; they aren't trended."""
    yes = lambda v: v if isinstance(v, bool) else None
    m, sec, g = raw["measurement"], raw["security"], raw["google_business"]
    m = m if isinstance(m, dict) else None
    pixels = ads_pixel(m) if m else None
    pixel_detail = (", ".join(pixels["pixels"]) if pixels["present"] else "none seen; a tag manager may load one"
                    if pixels["tag_manager"] else "no ad pixel from Meta, LinkedIn, Google Ads, TikTok, X, Bing or Pinterest") if m else ""
    return [("Analytics", yes(m.get("has_measurement")) if m else None, "?sort=analytics#pages", ""),
            ("Consent tool", yes(m.get("has_consent_tool")) if m else None, "?sort=analytics#pages", ""),
            ("Ad pixel", pixels["present"] if m else None, "#site", pixel_detail),
            ("HTTPS", yes(sec.get("https")) if isinstance(sec, dict) else None, "?sort=security#pages", ""),
            ("Google listing", bool(g.get("found")) if isinstance(g, dict) and g.get("status") != "UNKNOWN" else None, "#listing", "")]
```

Change `load()`'s signature and tail:

```python
def load(bundle, sort="issues", desc=False, earlier=None, history=()):
    """history: [(created_at, metrics)] of this site's earlier runs, oldest first, for the trend lines; the web app
    passes its stored snapshots. Default: none, so each tile shows only this run."""
```

and replace `model["tiles"] = tiles(model, raw)` (keeping the `model["metrics"]` line from Task 1 above it) with:

```python
    model["tiles"] = tiles(model, raw)
    runs = [*history, (manifest.get("created_at"), model["metrics"])]
    for t in model["tiles"]:
        t["trend"] = spark(runs, t["key"]) if t["key"] else None
    model["facts"] = facts(raw)
    model["ai_note"] = any(t["key"] in NOISY for t in model["tiles"])
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m unittest tests.test_dashboard -v`
Expected: `LoadTest` all PASS. (`DashboardPageTest.test_no_ad_pixel_hides_ads` runs only under Django and is fixed in Task 4.)

- [ ] **Step 5: Commit**

```bash
git add src/companyscan/web/dashboard.py tests/test_dashboard.py
git commit -m "Add trend lines, a yes/no state row and tiles for the AI and listing checks"
```

---

### Task 4: Render trends, state row and the Changes tab

**Files:**
- Modify: `src/companyscan/web/views.py` (`render_run` passes `history`)
- Modify: `src/companyscan/views/templates/dashboard.html` (nav, overview, tiles, move `#since` to `#changes`)
- Modify: `src/companyscan/views/static/app.css` (spark, trend, facts, tab highlight)
- Test: `tests/test_web.py`, `tests/test_dashboard.py` (`DashboardPageTest`)

**Interfaces:**
- Consumes: `load(..., history=...)`, tile `trend`, `m.facts`, `m.ai_note` (Task 3); `Snapshot.metrics` (Task 2).

- [ ] **Step 1: Write the failing tests.** In `tests/test_web.py` `WebTests`:

```python
    def test_site_page_shows_trends_state_row_and_changes_tab(self):
        for name, created, missing in (("acme-a", "2026-01-01T00:00:00+00:00", 2), ("acme-b", "2026-02-01T00:00:00+00:00", 0)):
            d = bundle(self.root, name, "https://acme.test/", created)
            (d / "technical").mkdir()
            (d / "technical/security.json").write_text(json.dumps(
                {"pages_checked": 1, "https": True, "missing_summary": [{"header": f"h{i}", "pages": 1} for i in range(missing)]}))
        self.client.get("/")  # sync()
        page = self.client.get(f"/site/{Site.objects.get(origin='https://acme.test').pk}").text
        self.assertIn('<svg class="spark"', page)
        self.assertIn('<p class="trend trend-better">+2 ▲</p>', page)  # 4/6 then 6/6 security headers.
        self.assertIn("<title>2026-01-01 4/6</title>", page)
        self.assertIn('<ul class="facts"', page)
        old = self.client.get("/run/acme-a").text  # An older run's page only charts runs up to it.
        self.assertNotIn("trend-better", old)
```

In `tests/test_dashboard.py` `DashboardPageTest.test_renders_since_last_run`, replace the first `assertIn("<summary>Since last run</summary>", page)` with:

```python
        self.assertIn('<section id="changes" class="tab">', page)
        self.assertIn('href="#changes"', page)
        self.assertNotIn("<summary>Since last run</summary>", page)
```

In `test_no_ad_pixel_hides_ads`, keep `self.assertIn("no ad pixel from Meta, LinkedIn", page)` (now the state row's hover text) and add:

```python
        self.assertIn('title="no ad pixel from Meta, LinkedIn, Google Ads, TikTok, X, Bing or Pinterest">✗ Ad pixel', page)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python manage.py test tests --top-level-directory tests`
Expected: the three tests above FAIL.

- [ ] **Step 3: Implement.**

`views.py` `render_run`, replace the `earlier = ...` statement with:

```python
    # Stored snapshots, so "Since last run" and the trend lines still find runs whose bundles were deleted.
    before = list(run.site.snapshots.filter(created_at__lt=run.created_at)) if run and run.created_at else None
    earlier = [(s.name, s.created_at.isoformat(), s.checks.get) for s in before] if before is not None else None
    history = [(s.created_at.isoformat(), s.metrics) for s in reversed(before or [])]  # Oldest first.
```

and pass it: `dashboard.load(view, sort, desc, earlier, history)`.

`dashboard.html` nav: after `<a href="#overview">Overview</a>` add `{% if m.since %}<a href="#changes">Changes</a>{% endif %}`.

After the closing `</section>` of `<section class="overview">` and before `<section class="tiles">`, add the state row:

```html
  <ul class="facts" aria-label="Current state">
    {% for label, value, href, detail in m.facts %}<li><a href="{{ href }}" class="fact-{{ 'yes' if value is sameas true else 'no' if value is sameas false else 'unknown' }}"{% if detail %} title="{{ detail }}"{% endif %}>{{ "✓" if value is sameas true else "✗" if value is sameas false else "—" }} {{ label }}</a></li>{% endfor %}
  </ul>
```

Inside the tile loop, after the `{% if t.status %}…{% endif %}` line:

```html
      {% if t.trend %}
      <p class="trend trend-{{ t.trend.trend or 'none' }}">{% if t.trend.delta %}{{ t.trend.delta }} {{ t.trend.arrow }}{% elif t.trend.trend == "same" %}No change{% else %}First run{% endif %}</p>
      <svg class="spark" viewBox="0 0 120 28" role="img" aria-label="{{ t.title }} over the last {{ t.trend.dots | length }} measured runs">{% for points in t.trend.lines %}<polyline points="{{ points }}"/>{% endfor %}{% for d in t.trend.dots %}<circle cx="{{ d.x }}" cy="{{ d.y }}" r="3"><title>{{ d.title }}</title></circle>{% endfor %}</svg>
      {% endif %}
```

After the tiles `</section>`: `{% if m.ai_note %}<p class="note">AI results: model answers vary between runs even with the same questions; look for changes that hold over several runs.</p>{% endif %}`

Cut the whole `{% if m.since %}<details id="since" open>…</details>{% endif %}` block out of the Overview. Paste it as a new tab right after the Overview's closing `</section>` (the one after the `#report` details), changing only its wrapper:

```html
  {% if m.since %}
  <section id="changes" class="tab"><h2>Changes since last run</h2>
    {# the original block's contents, from {% for c in m.since %} through the final <p class="note">Model answers vary…</p> #}
  </section>
  {% endif %}
```

That is: replace `<details id="since" open><summary>Since last run</summary>` with `<section id="changes" class="tab"><h2>Changes since last run</h2>` and the matching `</details>` with `</section>`; the inner markup is unchanged.

`app.css`: after the `.tile .chip` rule add:

```css
.tile .trend { margin: 0; font-size: 13px; font-weight: 600; }
.trend-better { color: var(--good); } .trend-worse { color: var(--critical); } .trend-same, .trend-none { color: var(--ink-3); }
.spark { width: 100%; height: 28px; overflow: visible; }
.spark polyline { fill: none; stroke: var(--accent); stroke-width: 1.5; }
.spark circle { fill: var(--accent); }
.facts { display: flex; flex-wrap: wrap; gap: 8px 16px; list-style: none; margin: 0 0 12px; padding: 0; font-size: 14px; font-weight: 600; }
.facts a { color: var(--ink-2); text-decoration: none; } .facts a:hover { color: var(--ink); }
.fact-yes { color: var(--good) !important; }
```

and extend the active-tab selector list (the rule ending `{ color: var(--ink); border-bottom-color: var(--accent); }`) with `.dash:has(#changes:target) .tabs a[href="#changes"],` as its first line.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python manage.py test tests --top-level-directory tests`
Expected: all PASS.

- [ ] **Step 5: Look at it.** `python manage.py runserver`, open a site with two or more runs: the Overview shows Anomalies, the ✓/✗ row, tiles with change and sparkline, and a Changes tab when an earlier run exists. Hover a sparkline dot: date and value.

- [ ] **Step 6: Commit**

```bash
git add src/companyscan/web/views.py src/companyscan/views/templates/dashboard.html src/companyscan/views/static/app.css tests/test_web.py tests/test_dashboard.py
git commit -m "Show trend lines and a yes/no row on the Overview; move run diffs to a Changes tab"
```

---

### Task 5: Docs

**Files:**
- Modify: `README.md` ("Tracking over time" and "Web UI")
- Modify: `docs/superpowers/specs/2026-09-29-score-trends-design.md` (record the planning refinements)

- [ ] **Step 1:** In README "Tracking over time", replace the paragraph starting "The dashboard's **Since last run** panel" with:

```markdown
The dashboard's **Changes** tab compares each check with the newest earlier run that has it. The UI keeps a small snapshot of each run in the database: its tracked checks (answers without their text, review stats without the reviews) and its headline numbers (`dashboard.METRICS`: pages, accessibility barriers, copy scores, analytics and SEO pass rates, JSON-LD share, security headers, AI rank and mention rate, answered questions, Google rating and more). So comparisons and trends still work after the earlier bundle is deleted. Each Overview tile shows its number's change since the last run that measured it (green when better, red when worse, grey when neither direction is better) and a sparkline of the last 12 runs; a run that didn't measure it is a gap, not a zero. Runs whose bundle was deleted before headline numbers were stored have none. Yes/no facts (analytics, consent tool, ad pixel, HTTPS, Google listing) show only their current state in a row above the tiles. Question-by-question rows appear only for questions asked both times. Model answers vary between runs even with the same questions, so small moves are noise: look for changes that hold over several runs.
```

- [ ] **Step 2:** In the spec, add under "Trend tiles" a short "Refined during planning" list copying the four bullets from this plan's "Deliberate refinements" section.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-09-29-score-trends-design.md
git commit -m "Document score trends"
```
