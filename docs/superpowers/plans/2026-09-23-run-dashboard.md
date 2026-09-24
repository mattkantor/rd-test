# Run Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/run/<bundle>` page to the local `companyscan serve` UI that shows everything one crawl bundle captured: headline cards on top, and a collapsible section per area below.

**Architecture:**
- **View model:** a new module, `web/dashboard.py`, reads the bundle files and turns them into plain dicts. Missing and unreadable files become marker strings, and two generic helpers (`describe`, `table`) turn any JSON report into fields and tables, so each technical file doesn't need its own code.
- **Page:** a Jinja template, `dashboard.html`, lays the view model out using native `<details>` sections, with no JavaScript.
- **Route:** the FastAPI route checks that the folder is a crawl bundle inside `output/` before rendering.

**Tech Stack:** Python 3.10+, FastAPI and Jinja2 (the existing `.[web]` extra, already in `.venv`), and `unittest` with FastAPI's `TestClient`.

**Spec:** `docs/superpowers/specs/2026-09-23-run-dashboard-design.md`

## Global Constraints

- No new dependencies and no JavaScript. Server-rendered Jinja plus CSS in `views/static/app.css`.
- All captured content is untrusted. Jinja autoescape stays on, `|safe` is never used, and only `http`/`https` URLs become `href`s, always with `rel="noopener noreferrer"` and `target="_blank"`.
- A missing file renders "not collected" and an unreadable file renders "unreadable". The page must never return 500 because of bundle contents.
- The route returns 404 unless the folder resolves inside the output root, has `manifest.json`, and that manifest has `counts`.
- Tests make no network calls. Run with: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
- This folder is not a git repo, so skip commit steps.

## Review Focus

1. **Corrupt JSON anywhere in the bundle:** the page still renders, showing "unreadable" for that part. Pinned in Task 1 (`read`) and Task 2 (the page).
2. **A tampered page `content_path` that escapes the bundle (`../../etc/passwd`):** it must not be linked, and must not cause a 500 (the `file_url` filter raises on paths outside the root). Pinned in Task 1.
3. **Captured HTML or script in text fields** (accessibility snippets, titles, answers): shown escaped. Pinned in Task 2.
4. **Non-web or malformed URLs** (`javascript:`, `data:`, `http://[`): shown as text, not linked. Pinned in Task 1.
5. **Large bundles:** generic tables stop at 200 rows with a "Showing N of M" note, and the pages table stays complete. Pinned in Task 1.

---

### Task 1: View model (`web/dashboard.py`)

**Files:**
- Create: `src/companyscan/web/dashboard.py`
- Test: `tests/test_dashboard.py` (the fixture builder plus loader tests. Task 2 adds page tests to the same file so they share the fixture. This departs from the spec, which named `test_web.py`.)

**Interfaces:**
- Consumes: `latest(bundle, name) -> Path | None` and `verify(bundle) -> list[str]` from `companyscan.report.analyze`.
- Produces:
  - Markers: `MISSING = "not collected"`, `UNREADABLE = "unreadable"`
  - `read(bundle, rel) -> object | MISSING | UNREADABLE`
  - `link(url) -> str | None`: http(s) only
  - `badge(value) -> str`: a CSS class for status words, or `""`
  - `table(items, limit=200) -> {"columns", "rows", "total", "shown"}`
  - `describe(data) -> {"state", "fields", "text", "tables": [(name, table)]}`
  - `load(bundle, sort="id", desc=False) -> dict`, with keys `manifest, integrity, header, report, pages, sort, desc, technical, accessibility, dimensions, reputation, social, company, coverage, cards`
  - Each card is `{"title", "anchor", "lines"}`. Each page row is `{"id", "url", "status", "label", "title", "depth", "ctas", "extraction", "json", "content"}`. `reputation` is one of: `{"state"}`, `{"state": None, "unknown"}`, `{"state": None, "legacy": {"answer", "competitors"}}`, or `{"state": None, "scores", "branded", "questions": [{"prompt", "source", "answers": [{..., "named"}]}]}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_dashboard.py`:

```python
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from companyscan.web.dashboard import MISSING, UNREADABLE, describe, link, load, read, table

SCORED = {
    "status": "COMPLETE", "domain": "acme.test", "error": None,
    "branded": {"raw_answer": "Acme Dental is a dentist.", "domain_mentioned": True},
    "prompts": [{"text": "best dentist?", "source": "generated"}],
    "answers": [{"prompt": "best dentist?", "sample": 1, "raw_answer": "Try Acme Dental or Beta.",
                 "companies": [{"name": "Acme Dental"}, {"name": "Beta"}, "junk"], "error": None}],
    "scores": {"rank": 1, "of": 2, "mention_rate": 1.0, "share_of_voice": 0.5, "answers_scored": 1, "answers_total": 1,
               "leaderboard": [{"company": "Acme Dental", "key": "acme.test", "mentions": 1, "avg_position": 1.0, "is_target": True},
                               {"company": "Beta", "key": "beta", "mentions": 1, "avg_position": 2.0, "is_target": False}],
               "sentiment": {"score": 42, "n": 2, "min": 20, "max": 60,
                             "branded": {"score": 60, "n": 1, "min": 60, "max": 60},
                             "unbranded": {"score": 20, "n": 1, "min": 20, "max": 20}}},
    "model": ["claude-x"], "limitations": ["one sample"],
}
LEGACY = {"raw_answer": "Acme is a dentist.", "domain_mentioned": True,
          "analysis": {"competitors": [{"name": "Beta", "website": "beta.test", "reason": "same city"}]}}


def write(d, rel, value):
    path = d / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    return rel


def full_bundle(root, name="acme", reputation=SCORED):
    d = Path(root) / name
    files = [
        write(d, "pages/0001.json", {"id": "0001", "url": "https://acme.test/", "status": 200, "classification": {"label": "homepage"},
                                     "title": "Acme home", "depth": 0, "ctas": [{"text": "Book"}], "extraction_status": "EXTRACTED",
                                     "content_path": "content/homepage.md"}),
        write(d, "pages/0002.json", {"id": "0002", "url": "javascript:alert(1)", "status": 404, "classification": {"label": "other"},
                                     "title": "Broken page", "depth": 2, "ctas": [], "extraction_status": "FAILED"}),
        write(d, "pages/0003.json", {"id": "0003", "url": "https://acme.test/about", "status": 200, "classification": {"label": "about"},
                                     "title": "About us", "depth": 1, "ctas": [], "extraction_status": "EXTRACTED",
                                     "content_path": "../../../etc/passwd"}),
        write(d, "content/homepage.md", "# Acme"),
        write(d, "technical/robots.json", {"status": 200, "policy_status": "OBSERVED", "text": "User-agent: *\nAllow: /"}),
        write(d, "technical/aeo.json", {"pages_checked": 3, "pages_with_json_ld": 2, "types": {"Dentist": 2},
                                        "issue_summary": [{"severity": "warning", "code": "missing_recommended", "pages": 2}]}),
        write(d, "technical/measurement.json", {"tools": [{"tool": "Google tag", "category": "analytics", "ids": ["G-1"]}],
                                                "has_measurement": True, "has_consent_tool": False}),
        write(d, "technical/social-preview.json", {"pages_checked": 3, "issue_summary": []}),
        write(d, "technical/redirects.json", []),
        write(d, "technical/accessibility.json", {
            "automated_status": "WARNING", "conformance_status": "UNKNOWN", "pages_checked": 3, "finding_count": 1,
            "findings": [{"rule_id": "image-alt", "severity": "WARNING", "url": "https://acme.test/",
                          "wcag": {"criterion": "1.1.1", "level": "A"}, "evidence": {"line": 3, "html": "<img src=x onerror=alert(1)>"}}]}),
        write(d, "technical/security.json", {"pages_checked": 3, "https": True,
                                             "missing_summary": [{"header": "content-security-policy", "pages": 3}]}),
        write(d, "technical/fonts.json", {"distinct_families": 2, "families": [{"family": "Inter", "pages": 3}]}),
        write(d, "technical/llm_reputation.json", reputation),
        write(d, "social/discovered.json", {"profiles": [{"network": "linkedin", "url": "https://www.linkedin.com/company/acme",
                                                          "evidence": [{"source": "https://acme.test/"}]}]}),
        write(d, "company.json", {"names": [{"value": "Acme Dental", "kind": "EXTRACTED", "source": "https://acme.test/"}]}),
        write(d, "urls.json", {"skipped": [{"url": "https://acme.test/cart", "reason": "excluded_path"}]}),
    ]
    artifacts = [{"path": f, "sha256": hashlib.sha256((d / f).read_bytes()).hexdigest()} for f in files]
    write(d, "manifest.json", {"input_url": "https://acme.test/", "created_at": "2026-09-23T12:00:00+00:00", "status": "PARTIAL",
                               "command": "scan", "config": {"max_pages": 50, "max_depth": 3,
                                                             "dimensions": ["security", "fonts", "llm_reputation"]},
                               "counts": {"pages": 3, "extracted_pages": 2, "profiles": 1, "skipped": 1},
                               "errors": [{"url": "https://acme.test/x", "error": "timeout"}],
                               "artifacts": artifacts, "limitations": ["Public HTML only"]})
    write(d, "analysis/report.md", "# Acme report")
    write(d, "analysis/analysis.json", {"findings": [{"id": "F1", "severity": "WARNING", "title": "Thin proof"}]})
    return d


class HelperTest(unittest.TestCase):
    def test_read_missing_and_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp), "bad.json", "{nope")
            write(Path(tmp), "good.json", {"a": 1})
            self.assertEqual(read(tmp, "absent.json"), MISSING)
            self.assertEqual(read(tmp, "bad.json"), UNREADABLE)
            self.assertEqual(read(tmp, "good.json"), {"a": 1})

    def test_link_allows_only_web_urls(self):
        self.assertEqual(link("https://acme.test/x"), "https://acme.test/x")
        self.assertEqual(link(" http://acme.test "), "http://acme.test")
        for bad in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x", "http://[bad", "/relative", 42, None):
            self.assertIsNone(link(bad), bad)

    def test_table_flattens_one_level_and_limits_rows(self):
        items = [{"rule": "alt", "wcag": {"criterion": "1.1.1"}, "evidence": [1, 2], "deep": {"a": {"b": 1}}}] * 3 + ["junk"]
        t = table(items, limit=2)
        self.assertEqual(t["columns"], ["rule", "wcag.criterion", "evidence", "deep"])
        self.assertEqual(t["rows"][0], ["alt", "1.1.1", "2 items", "1 fields"])
        self.assertEqual((t["shown"], t["total"]), (2, 4))
        self.assertEqual(table(None), {"columns": [], "rows": [], "total": 0, "shown": 0})

    def test_describe_splits_fields_text_and_tables(self):
        d = describe({"a": 1, "text": "hi", "tools": [{"x": 1}], "types": {"Dentist": 2}, "ids": ["G-1"], "empty": [],
                      "nested": {"k": {"z": 1}}})
        self.assertEqual(d["fields"], {"a": 1, "ids": "G-1", "empty": "none", "nested": "1 fields"})
        self.assertEqual(d["text"], "hi")
        self.assertEqual([name for name, _ in d["tables"]], ["tools", "types"])
        self.assertEqual(describe([{"u": 1}])["tables"][0][0], "items")
        self.assertEqual(describe(MISSING)["state"], MISSING)


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundle = full_bundle(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_header_integrity_report_and_cards(self):
        m = load(self.bundle)
        self.assertEqual((m["header"]["host"], m["header"]["status"], m["header"]["errors"]), ("acme.test", "PARTIAL", 1))
        self.assertEqual(m["integrity"], [])
        self.assertEqual(m["report"]["findings"], [{"id": "F1", "verdict": "WARNING", "title": "Thin proof"}])
        self.assertEqual(m["report"]["md"].name, "report.md")
        cards = {c["title"]: c["lines"] for c in m["cards"]}
        self.assertEqual(list(cards), ["Crawl", "Report", "Accessibility", "Analytics", "AEO", "Social previews",
                                       "Security", "Fonts", "AI reputation"])  # Meta ads not collected: no card.
        self.assertEqual(cards["Crawl"], ["3 pages", "1 skipped", "Errors: 1"])
        self.assertEqual(cards["Security"], ["HTTPS everywhere", "Most missing: content-security-policy (3 pages)"])
        self.assertEqual(cards["AI reputation"], ["#1 of 2", "Sentiment +42"])

    def test_sections(self):
        m = load(self.bundle)
        self.assertEqual([t["name"] for t in m["technical"]][:3], ["robots", "sitemap", "crawler-access"])
        robots, sitemap = m["technical"][0], m["technical"][1]
        self.assertEqual((robots["state"], robots["text"]), (None, "User-agent: *\nAllow: /"))
        self.assertEqual(sitemap["state"], MISSING)
        self.assertEqual(m["dimensions"]["meta_ads"]["state"], MISSING)
        self.assertIn("wcag.criterion", dict(m["accessibility"]["tables"])["findings"]["columns"])
        self.assertEqual(m["reputation"]["scores"]["rank"], 1)
        self.assertEqual(m["reputation"]["questions"][0]["answers"][0]["named"], "Acme Dental, Beta")
        self.assertEqual(m["coverage"]["skipped"]["rows"], [["https://acme.test/cart", "excluded_path"]])
        self.assertEqual(m["coverage"]["limitations"], ["Public HTML only"])
        self.assertEqual(dict(m["company"]["tables"])["names"]["rows"][0][0], "Acme Dental")

    def test_pages_rows_sorting_and_safe_content_links(self):
        write(self.bundle, "pages/0004.json", "{corrupt")
        ids = lambda m: [p["id"] for p in m["pages"]]
        m = load(self.bundle)
        self.assertEqual(ids(m), ["0001", "0002", "0003", "0004"])
        self.assertEqual((m["pages"][0]["ctas"], m["pages"][0]["content"]), (1, "content/homepage.md"))
        self.assertIsNone(m["pages"][2]["content"])  # content_path escaping the bundle is dropped.
        self.assertEqual(m["pages"][3]["label"], UNREADABLE)
        self.assertEqual(ids(load(self.bundle, "title")), ["0003", "0001", "0002", "0004"])  # Missing title sorts last.
        self.assertEqual(ids(load(self.bundle, "title", desc=True))[:3], ["0004", "0002", "0001"])
        self.assertEqual(ids(load(self.bundle, "depth")), ["0001", "0003", "0002", "0004"])
        bogus = load(self.bundle, "bogus")
        self.assertEqual((ids(bogus), bogus["sort"]), (["0001", "0002", "0003", "0004"], "id"))

    def test_integrity_problem_is_reported(self):
        write(self.bundle, "pages/0001.json", {"tampered": True})
        self.assertEqual(load(self.bundle)["integrity"], ["modified: pages/0001.json"])

    def test_reputation_legacy_unknown_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = load(full_bundle(tmp, "old", LEGACY))
            self.assertEqual(legacy["reputation"]["legacy"]["answer"], "Acme is a dentist.")
            self.assertEqual(legacy["reputation"]["legacy"]["competitors"]["rows"][0][0], "Beta")
            self.assertIn("No ranking in this run", {c["title"]: c["lines"] for c in legacy["cards"]}["AI reputation"])
            failed = load(full_bundle(tmp, "failed", {"status": "UNKNOWN", "reason": "llm_request_failed", "error": "no claude"}))
            self.assertEqual(failed["reputation"]["unknown"], "no claude")
            gone = full_bundle(tmp, "gone")
            (gone / "technical/llm_reputation.json").unlink()
            m = load(gone)
            self.assertEqual(m["reputation"], {"state": MISSING})
            self.assertNotIn("AI reputation", [c["title"] for c in m["cards"]])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_dashboard -v`
Expected: ERROR `ModuleNotFoundError: No module named 'companyscan.web.dashboard'`

- [ ] **Step 3: Implement**

`src/companyscan/web/dashboard.py`:

```python
"""Dashboard view model: read one crawl bundle into plain dicts the template lays out. Captured data is untrusted."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from ..report.analyze import latest, verify

MISSING, UNREADABLE = "not collected", "unreadable"
SORTS = ("id", "status", "label", "title", "depth")
TECHNICAL = ["robots", "sitemap", "crawler-access", "indexing", "redirects", "headers", "schema", "aeo",
             "measurement", "social-preview", "llms", "feeds"]
DIMENSIONS = ["security", "fonts", "meta_ads", "llm_reputation"]
STATUSES = {"PASS", "WARNING", "FAIL", "UNKNOWN", "COMPLETE", "PARTIAL", "ERROR", "OBSERVED"}


def read(bundle, rel):
    path = Path(bundle) / rel
    if not path.is_file():
        return MISSING
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UNREADABLE


def link(url):
    """Only http(s) URLs from captured data become hrefs; javascript:, data: and malformed URLs render as text."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
        ok = parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)
    except ValueError:
        return None
    return url.strip() if ok else None


def badge(value):
    return f"st st-{value.lower()}" if isinstance(value, str) and value in STATUSES else ""


def cell(value):
    if isinstance(value, list):
        return f"{len(value)} items"
    if isinstance(value, dict):
        return f"{len(value)} fields"
    return value


def flatten(item):
    """One level of nesting becomes dotted columns (wcag.criterion); deeper structure becomes a count."""
    out = {}
    for key, value in item.items():
        if isinstance(value, dict) and value and all(not isinstance(v, (dict, list)) for v in value.values()):
            out.update({f"{key}.{sub}": v for sub, v in value.items()})
        else:
            out[key] = cell(value)
    return out


def table(items, limit=200):
    items = items if isinstance(items, list) else []
    rows = [flatten(i) for i in items[:limit] if isinstance(i, dict)]
    columns = list(dict.fromkeys(k for r in rows for k in r))
    return {"columns": columns, "rows": [[r.get(c) for c in columns] for r in rows], "total": len(items), "shown": len(rows)}


def describe(data):
    """Generic view of any report: scalar fields, a `text` body, and a table per list or flat dict."""
    if data in (MISSING, UNREADABLE):
        return {"state": data, "fields": {}, "text": None, "tables": []}
    if isinstance(data, list):
        return {"state": None, "fields": {}, "text": None, "tables": [("items", table(data))]}
    if not isinstance(data, dict):
        return {"state": None, "fields": {"value": cell(data)}, "text": None, "tables": []}
    fields, tables = {}, []
    for key, value in data.items():
        if key == "text" and isinstance(value, str):
            continue
        if isinstance(value, list) and any(isinstance(i, dict) for i in value):
            tables.append((key, table(value)))
        elif isinstance(value, dict) and value and all(not isinstance(v, (dict, list)) for v in value.values()):
            tables.append((key, table([{"name": k, "value": v} for k, v in value.items()])))
        elif isinstance(value, list):
            fields[key] = ", ".join(map(str, value[:20])) + (" …" if len(value) > 20 else "") if value else "none"
        else:
            fields[key] = cell(value)
    return {"state": None, "fields": fields, "text": data.get("text") if isinstance(data.get("text"), str) else None,
            "tables": tables}


def sort_key(value):
    """None last; strings and numbers never compared with each other (tampered files can mix them)."""
    number = value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
    return value is None, isinstance(value, str), value.lower() if isinstance(value, str) else number


def pages(bundle, sort="id", desc=False):
    bundle, rows = Path(bundle), []
    for path in sorted((bundle / "pages").glob("*.json")):
        p = read(bundle, f"pages/{path.name}")
        if not isinstance(p, dict):
            rows.append({"id": path.stem, "url": None, "status": None, "label": UNREADABLE, "title": None, "depth": None,
                         "ctas": 0, "extraction": None, "json": f"pages/{path.name}", "content": None})
            continue
        content = p.get("content_path")
        # file_url raises on paths outside the output root; a tampered content_path must not 500 the page.
        safe = isinstance(content, str) and (bundle / content).resolve().is_relative_to(bundle.resolve())
        rows.append({"id": p.get("id", path.stem), "url": p.get("url"), "status": p.get("status"),
                     "label": (p.get("classification") or {}).get("label") if isinstance(p.get("classification"), dict) else None,
                     "title": p.get("title"), "depth": p.get("depth"), "ctas": len(p["ctas"]) if isinstance(p.get("ctas"), list) else 0,
                     "extraction": p.get("extraction_status"), "json": f"pages/{path.name}", "content": content if safe else None})
    key = sort if sort in SORTS else "id"
    return sorted(rows, key=lambda r: sort_key(r[key]), reverse=desc)


def report(bundle):
    path = latest(bundle, "analysis.json")
    analysis = read(path.parent, path.name) if path else MISSING
    found = analysis.get("findings") if isinstance(analysis, dict) else None
    findings = [{"id": f.get("id"), "verdict": f.get("verdict") or f.get("severity"), "title": f.get("title")}
                for f in (found if isinstance(found, list) else []) if isinstance(f, dict)]
    return {"md": latest(bundle, "report.md"), "pdf": latest(bundle, "report.pdf"), "analysis": path, "findings": findings}


def reputation(data):
    if data in (MISSING, UNREADABLE) or not isinstance(data, dict):
        return {"state": data if data in (MISSING, UNREADABLE) else UNREADABLE}
    if data.get("status") == "UNKNOWN":
        return {"state": None, "unknown": data.get("error") or data.get("reason")}
    if not isinstance(data.get("scores"), dict):  # Runs from before ranking: one branded answer.
        competitors = (data.get("analysis") or {}).get("competitors") if isinstance(data.get("analysis"), dict) else None
        return {"state": None, "legacy": {"answer": data.get("raw_answer"), "competitors": table(competitors)}}
    answers = [a for a in data.get("answers") or [] if isinstance(a, dict)]
    for a in answers:
        named = a.get("companies") if isinstance(a.get("companies"), list) else []
        a["named"] = ", ".join(c["name"] for c in named if isinstance(c, dict) and isinstance(c.get("name"), str))
    questions = [{"prompt": p.get("text"), "source": p.get("source"), "answers": [a for a in answers if a.get("prompt") == p.get("text")]}
                 for p in data.get("prompts") or [] if isinstance(p, dict)]
    return {"state": None, "scores": data["scores"], "branded": data.get("branded") or {}, "questions": questions}


def card(title, anchor, *lines):
    return {"title": title, "anchor": anchor, "lines": [line for line in lines if line]}


def cards(model, raw):
    m, out = model["manifest"], []
    counts = m.get("counts") or {}
    out.append(card("Crawl", "coverage", f"{counts.get('pages', 0)} pages", f"{counts.get('skipped', 0)} skipped",
                    f"Errors: {len(m.get('errors') or [])}"))
    r = model["report"]
    out.append(card("Report", "report", "report.md ready" if r["md"] else "No report yet", "PDF ready" if r["pdf"] else ""))
    t = raw["accessibility"]
    if isinstance(t, dict):
        out.append(card("Accessibility", "accessibility", str(t.get("automated_status")),
                        f"{t.get('finding_count', 0)} potential issues", f"{t.get('pages_checked', 0)} pages checked"))
    t = raw["measurement"]
    if isinstance(t, dict):
        out.append(card("Analytics", "technical", f"{len(t.get('tools') or [])} tools",
                        "Consent tool found" if t.get("has_consent_tool") else "No consent tool"))
    t = raw["aeo"]
    if isinstance(t, dict):
        out.append(card("AEO", "technical", f"{t.get('pages_with_json_ld', 0)} of {t.get('pages_checked', 0)} pages with JSON-LD",
                        f"{len(t.get('issue_summary') or [])} issue types"))
    t = raw["social-preview"]
    if isinstance(t, dict):
        out.append(card("Social previews", "technical", f"{len(t.get('issue_summary') or [])} issue types"))
    t = raw["security"]
    if isinstance(t, dict):
        top = (t.get("missing_summary") or [None])[0]
        top = top if isinstance(top, dict) and top.get("header") else None
        out.append(card("Security", "security", {True: "HTTPS everywhere", False: "Not all HTTPS"}.get(t.get("https"), "HTTPS unknown"),
                        f"Most missing: {top['header']} ({top.get('pages')} pages)" if top else "No missing headers"))
    t = raw["fonts"]
    if isinstance(t, dict):
        out.append(card("Fonts", "fonts", f"{t.get('distinct_families', 0)} font families"))
    t = raw["meta_ads"]
    if isinstance(t, dict):
        out.append(card("Meta ads", "meta_ads", str(t.get("status")),
                        f"{t['ad_count']} ads" if "ad_count" in t else str(t.get("reason") or "")))
    rep = model["reputation"]
    if rep.get("scores") is not None:
        s = rep["scores"]
        sentiment = (s.get("sentiment") or {}).get("score")
        out.append(card("AI reputation", "reputation", f"#{s['rank']} of {s.get('of')}" if s.get("rank") else f"Unranked of {s.get('of', 0)}",
                        f"Sentiment {sentiment:+d}" if isinstance(sentiment, int) else "Sentiment n/a"))
    elif "legacy" in rep:
        out.append(card("AI reputation", "reputation", "No ranking in this run"))
    elif "unknown" in rep:
        out.append(card("AI reputation", "reputation", "Request failed"))
    return out


def load(bundle, sort="id", desc=False):
    bundle = Path(bundle)
    manifest = read(bundle, "manifest.json")
    manifest = manifest if isinstance(manifest, dict) else {}
    try:
        integrity = verify(bundle)
    except (OSError, ValueError, KeyError, TypeError):
        integrity = UNREADABLE
    raw = {name: read(bundle, f"technical/{name}.json") for name in TECHNICAL + ["accessibility"] + DIMENSIONS}
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    urls = read(bundle, "urls.json")
    model = {
        "manifest": manifest, "integrity": integrity,
        "header": {"host": urlsplit(str(manifest.get("input_url", ""))).netloc or manifest.get("input_url"),
                   "created_at": manifest.get("created_at", ""), "status": manifest.get("status"), "command": manifest.get("command"),
                   "counts": manifest.get("counts") or {}, "max_pages": config.get("max_pages"), "max_depth": config.get("max_depth"),
                   "dimensions": config.get("dimensions") or [], "errors": len(manifest.get("errors") or [])},
        "report": report(bundle),
        "pages": pages(bundle, sort, desc), "sort": sort if sort in SORTS else "id", "desc": desc,
        "technical": [{"name": n, "file": f"technical/{n}.json", **describe(raw[n])} for n in TECHNICAL],
        "accessibility": describe(raw["accessibility"]),
        "dimensions": {n: describe(raw[n]) for n in ("security", "fonts", "meta_ads")},
        "reputation": reputation(raw["llm_reputation"]),
        "social": describe(read(bundle, "social/discovered.json")),
        "company": describe(read(bundle, "company.json")),
        "coverage": {"skipped": table(urls.get("skipped") if isinstance(urls, dict) else None),
                     "errors": table(manifest.get("errors")), "limitations": manifest.get("limitations") or []},
    }
    model["cards"] = cards(model, raw)
    return model
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_dashboard -v`
Expected: 9 tests OK.

---

### Task 2: Route, template, styles and home link

**Files:**
- Modify: `src/companyscan/web/app.py`. Import `dashboard`, add a module-level `bundle_path`, use it in `/report`, register the `href` and `badge` filters, and add `GET /run/{name}`.
- Create: `src/companyscan/views/templates/dashboard.html`
- Modify: `src/companyscan/views/static/app.css` (append the dashboard styles)
- Modify: `src/companyscan/views/templates/index.html` (add a Dashboard link to the Files cell)
- Modify: `README.md` (the `## Web UI` section: one paragraph)
- Test: `tests/test_dashboard.py` (append `DashboardPageTest`)

**Interfaces:**
- Consumes: from Task 1, `dashboard.read`, `dashboard.load(bundle, sort, desc)`, `dashboard.link`, `dashboard.badge` and the model keys listed there.
- Produces: `bundle_path(root, name) -> Path | None` (resolved) in `web/app.py`, and the `/run/{name}` route.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard.py`, before the `if __name__` block:

```python
try:
    from fastapi.testclient import TestClient
    from companyscan.web.app import create_app
except ImportError:  # The UI is an optional extra: pip install -e '.[web]'
    TestClient = None


@unittest.skipUnless(TestClient, "FastAPI not installed")
class DashboardPageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = TestClient(create_app(self.root), base_url="http://127.0.0.1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_renders_every_section_safely(self):
        full_bundle(self.root)
        page = self.client.get("/run/acme")
        self.assertEqual(page.status_code, 200)
        for anchor in ("report", "pages", "technical", "accessibility", "security", "fonts", "meta_ads", "reputation",
                       "social", "coverage"):
            self.assertIn(f'id="{anchor}"', page.text)
        self.assertIn("#1 of 2", page.text)
        self.assertIn("+42", page.text)
        self.assertIn('class="target"', page.text)
        self.assertIn("not collected", page.text)  # meta_ads
        self.assertIn('href="/files/acme/analysis/report.md"', page.text)
        self.assertIn('href="https://acme.test/about" rel="noopener noreferrer"', page.text)
        self.assertNotIn('href="javascript:', page.text)
        self.assertIn("javascript:alert(1)", page.text)  # Shown as text.
        self.assertNotIn("<img src=x onerror", page.text)
        self.assertIn("&lt;img src=x onerror", page.text)
        self.assertIn("all artifacts verified", page.text)
        self.assertIn('href="/run/acme"', self.client.get("/").text)

    def test_not_found(self):
        full_bundle(self.root)
        (self.root / "rep").mkdir()
        (self.root / "rep/manifest.json").write_text(json.dumps({"input_url": "acme.test"}))  # Reputation-only bundle.
        for path in ("/run/nope", "/run/..%2F..%2Fetc", "/run/rep"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_sorting_and_unreadable_files(self):
        d = full_bundle(self.root)
        write(d, "pages/0004.json", "{corrupt")
        write(d, "technical/aeo.json", "{corrupt")
        order = lambda text: [text.index(t) for t in ("About us", "Acme home", "Broken page")]
        by_title = self.client.get("/run/acme?sort=title")
        self.assertEqual(by_title.status_code, 200)
        self.assertEqual(order(by_title.text), sorted(order(by_title.text)))
        reverse = order(self.client.get("/run/acme?sort=title&desc=1").text)
        self.assertEqual(reverse, sorted(reverse, reverse=True))
        page = self.client.get("/run/acme?sort=bogus")
        self.assertEqual(page.status_code, 200)
        self.assertIn("unreadable", page.text)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_dashboard.DashboardPageTest -v`
Expected: FAIL. `/run/acme` returns 404 because the route doesn't exist yet, and the home page has no Dashboard link.

- [ ] **Step 3: Implement the route**

In `src/companyscan/web/app.py`:

Change `from . import jobs` to `from . import dashboard, jobs`.

Add after `local_time`:

```python
def bundle_path(root, name):
    """Resolved bundle directory inside root that has a manifest.json, or None (blocks ../ escapes)."""
    bundle = (Path(root) / name).resolve()
    return bundle if bundle.is_relative_to(Path(root).resolve()) and (bundle / "manifest.json").is_file() else None
```

After the `file_url` filter line, add:

```python
    templates.env.filters["href"] = dashboard.link
    templates.env.filters["badge"] = dashboard.badge
```

In `report()`, replace the first two lines of the body:

```python
        bundle = bundle_path(root, dir)
        if not bundle:
            return back("Unknown crawl.")
```

Add after the `report` route:

```python
    @app.get("/run/{name}")
    def run_dashboard(request: Request, name: str, sort: str = "id", desc: bool = False):
        bundle = bundle_path(root, name)
        manifest = dashboard.read(bundle, "manifest.json") if bundle else None
        if not (isinstance(manifest, dict) and "counts" in manifest):  # Crawl bundles only.
            raise HTTPException(404)
        # Render from root/name, not the resolved path: file_url is relative to the unresolved root (macOS /var symlink).
        view = root / name
        return templates.TemplateResponse(request, "dashboard.html", {"m": dashboard.load(view, sort, desc), "bundle": view})
```

- [ ] **Step 4: Create the template**

`src/companyscan/views/templates/dashboard.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ m.header.host }} · Company Footprint</title>
  <link rel="stylesheet" href="{{ url_for('static', path='app.css') }}">
</head>
<body>
{% macro val(v) -%}
  {%- set h = v | href -%}
  {%- if h %}<a href="{{ h }}" rel="noopener noreferrer" target="_blank">{{ v }}</a>
  {%- elif v is none %}—
  {%- elif v is sameas true %}yes{% elif v is sameas false %}no
  {%- else %}<span class="{{ v | badge }}">{{ v }}</span>{% endif -%}
{%- endmacro %}
{% macro signed(x) %}{% if x is number %}{{ "%+d" | format(x) }}{% else %}—{% endif %}{% endmacro %}
{% macro pct(x) %}{% if x is number %}{{ "%.0f%%" | format(x * 100) }}{% else %}—{% endif %}{% endmacro %}
{% macro raw(rel) %}<a class="raw" href="{{ (bundle / rel) | file_url }}">raw JSON</a>{% endmacro %}
{% macro tbl(t) -%}
  {%- if t.rows %}
  <div class="scroll"><table class="data">
    <thead><tr>{% for c in t.columns %}<th>{{ c }}</th>{% endfor %}</tr></thead>
    <tbody>{% for row in t.rows %}<tr>{% for v in row %}<td>{{ val(v) }}</td>{% endfor %}</tr>{% endfor %}</tbody>
  </table></div>
  {%- if t.shown < t.total %}<small>Showing {{ t.shown }} of {{ t.total }}; see the raw file for the rest.</small>{% endif %}
  {%- else %}<p class="muted">None.</p>{% endif -%}
{%- endmacro %}
{% macro described(d, rel) -%}
  {%- if d.state %}<p class="muted">{{ d.state }}.</p>
  {%- else %}
    {%- if d.fields %}<dl class="fields">{% for k, v in d.fields.items() %}<dt>{{ k }}</dt><dd>{{ val(v) }}</dd>{% endfor %}</dl>{% endif %}
    {%- if d.text %}<pre>{{ d.text }}</pre>{% endif %}
    {%- for name, t in d.tables %}<h4>{{ name }}</h4>{{ tbl(t) }}{% endfor %}
    {{ raw(rel) }}
  {%- endif -%}
{%- endmacro %}
<main class="dash">
  <p><a href="/">← All sites</a></p>
  <h1>{{ m.header.host }}</h1>
  <p class="meta">
    {{ m.header.created_at | local_time }} · <span class="{{ m.header.status | badge }}">{{ m.header.status }}</span>
    · {{ m.header.command }} · {{ m.header.counts.pages or 0 }} pages · max {{ m.header.max_pages }} pages, depth {{ m.header.max_depth }}
    {% if m.header.dimensions %}· {{ m.header.dimensions | join(", ") }}{% endif %}
    · errors: {{ m.header.errors }} · <a href="{{ (bundle / 'manifest.json') | file_url }}">manifest</a>
  </p>
  <p class="meta">Integrity:
    {% if m.integrity == [] %}<span class="st st-pass">all artifacts verified</span>
    {% elif m.integrity is string %}<span class="st st-unknown">{{ m.integrity }}</span>
    {% else %}<span class="st st-fail">{{ m.integrity | length }} problem(s)</span>: {{ m.integrity | join("; ") }}{% endif %}
  </p>

  <section class="cards">
    {% for c in m.cards %}<a class="card" href="#{{ c.anchor }}"><h3>{{ c.title }}</h3>{% for line in c.lines %}<p>{{ line }}</p>{% endfor %}</a>{% endfor %}
  </section>

  <details id="report" open><summary>Report &amp; findings</summary>
    {% if m.report.md %}
      <p><a href="{{ m.report.md | file_url }}">report.md</a>
        {% if m.report.pdf %} · <a href="{{ m.report.pdf | file_url }}"><b>PDF</b></a>{% endif %}
        {% if m.report.analysis %} · <a href="{{ m.report.analysis | file_url }}">analysis.json</a>{% endif %}</p>
    {% else %}
      <p class="muted">No report yet.</p>
      <form method="post" action="/report"><input type="hidden" name="dir" value="{{ bundle.name }}"><button>Generate report</button></form>
    {% endif %}
    {% if m.report.findings %}
      <table class="data"><thead><tr><th>ID</th><th>Verdict</th><th>Finding</th></tr></thead><tbody>
      {% for f in m.report.findings %}<tr><td>{{ f.id }}</td><td>{{ val(f.verdict) }}</td><td>{{ f.title }}</td></tr>{% endfor %}
      </tbody></table>
    {% endif %}
  </details>

  <details id="pages"{% if m.sort != "id" or m.desc %} open{% endif %}><summary>Pages ({{ m.pages | length }})</summary>
    <div class="scroll"><table class="data"><thead><tr>
      {% for key, label in [("id", "#"), ("status", "Status"), ("label", "Type"), ("title", "Title"), ("depth", "Depth")] %}
      <th><a href="?sort={{ key }}{% if m.sort == key and not m.desc %}&desc=1{% endif %}#pages">{{ label }}{% if m.sort == key %} {{ "▼" if m.desc else "▲" }}{% endif %}</a></th>
      {% endfor %}
      <th>URL</th><th>CTAs</th><th>Extraction</th><th>Files</th></tr></thead>
      <tbody>{% for p in m.pages %}<tr>
        <td>{{ p.id }}</td><td>{{ val(p.status) }}</td><td>{{ val(p.label) }}</td><td>{{ val(p.title) }}</td><td>{{ val(p.depth) }}</td>
        <td>{{ val(p.url) }}</td><td>{{ p.ctas }}</td><td>{{ val(p.extraction) }}</td>
        <td><a href="{{ (bundle / p.json) | file_url }}">json</a>{% if p.content %} <a href="{{ (bundle / p.content) | file_url }}">text</a>{% endif %}</td>
      </tr>{% endfor %}</tbody>
    </table></div>
  </details>

  <details id="technical"><summary>Technical</summary>
    {% for t in m.technical %}<h3>{{ t.name }}</h3>{{ described(t, t.file) }}{% endfor %}
  </details>

  <details id="accessibility"><summary>Accessibility</summary>
    {{ described(m.accessibility, "technical/accessibility.json") }}
    {% if not m.accessibility.state %}<p><a href="{{ (bundle / 'technical/accessibility.md') | file_url }}">accessibility.md</a></p>{% endif %}
  </details>

  <details id="security"><summary>Security</summary>{{ described(m.dimensions.security, "technical/security.json") }}</details>
  <details id="fonts"><summary>Fonts</summary>{{ described(m.dimensions.fonts, "technical/fonts.json") }}</details>
  <details id="meta_ads"><summary>Meta ads</summary>{{ described(m.dimensions.meta_ads, "technical/meta_ads.json") }}</details>

  {% set r = m.reputation %}
  <details id="reputation"><summary>AI reputation</summary>
    {% if r.state %}<p class="muted">{{ r.state }}.</p>
    {% elif r.unknown is defined %}<p><span class="st st-unknown">UNKNOWN</span>: {{ r.unknown }}</p>
    {% elif r.legacy is defined %}
      <p class="muted">No ranking in this run.</p>
      <h4>Branded answer</h4><pre>{{ r.legacy.answer }}</pre>
      <h4>Competitors</h4>{{ tbl(r.legacy.competitors) }}
    {% else %}{% set s = r.scores %}
      <p class="big">{% if s.rank %}#{{ s.rank }} of {{ s.of }}{% else %}Unranked ({{ s.of }} companies named){% endif %}</p>
      <dl class="fields">
        <dt>Mention rate</dt><dd>{{ pct(s.mention_rate) }}</dd>
        <dt>Share of voice</dt><dd>{{ pct(s.share_of_voice) }}</dd>
        <dt>Answers scored</dt><dd>{{ s.answers_scored }} of {{ s.answers_total }}</dd>
        <dt>Sentiment</dt><dd>{{ signed(s.sentiment.score) }} (n={{ s.sentiment.n }})</dd>
        <dt>Branded</dt><dd>{{ signed(s.sentiment.branded.score) }} (n={{ s.sentiment.branded.n }})</dd>
        <dt>Unbranded</dt><dd>{{ signed(s.sentiment.unbranded.score) }} (n={{ s.sentiment.unbranded.n }})</dd>
      </dl>
      <h4>Leaderboard</h4>
      <table class="data"><thead><tr><th>#</th><th>Company</th><th>Mentions</th><th>Avg position</th></tr></thead><tbody>
      {% for row in s.leaderboard %}<tr{% if row.is_target %} class="target"{% endif %}><td>{{ loop.index }}</td><td>{{ row.company }}</td><td>{{ row.mentions }}</td><td>{{ row.avg_position }}</td></tr>{% endfor %}
      </tbody></table>
      <h4>Branded answer</h4><pre>{{ r.branded.raw_answer }}</pre>
      <h4>Buyer questions</h4>
      {% for q in r.questions %}
        <details class="nested"><summary>{{ q.prompt }} <small>{{ q.source }} · {{ q.answers | length }} answers</small></summary>
        {% for a in q.answers %}
          <div class="answer"><small>Sample {{ a.sample }}{% if a.named %} · named: {{ a.named }}{% endif %}</small>
          {% if a.error %}<p class="st st-fail">{{ a.error }}</p>{% else %}<pre>{{ a.raw_answer }}</pre>{% endif %}</div>
        {% endfor %}
        </details>
      {% endfor %}
    {% endif %}
    {% if not r.state %}{{ raw("technical/llm_reputation.json") }}{% endif %}
  </details>

  <details id="social"><summary>Social &amp; identity</summary>
    <h3>Profiles</h3>{{ described(m.social, "social/discovered.json") }}
    <h3>Company names</h3>{{ described(m.company, "company.json") }}
  </details>

  <details id="coverage"><summary>Coverage &amp; limits</summary>
    <h3>Skipped URLs</h3>{{ tbl(m.coverage.skipped) }}
    <h3>Errors</h3>{{ tbl(m.coverage.errors) }}
    <h3>Limitations</h3><ul>{% for l in m.coverage.limitations %}<li>{{ l }}</li>{% endfor %}</ul>
  </details>
</main>
</body>
</html>
```

- [ ] **Step 5: Add the styles and the home link**

Append to `src/companyscan/views/static/app.css`, above the `@media` block:

```css
.dash h1 { margin-bottom: 4px; }
.meta { color: #5d6470; font-size: 14px; margin: 4px 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }
.card { display: block; background: #fff; border: 1px solid #dfe2e7; border-radius: 10px; padding: 12px 14px; color: inherit; text-decoration: none; }
.card:hover { border-color: #2b50d6; }
.card h3 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: #5d6470; }
.card p { margin: 0; font-size: 14px; }
details { background: #fff; border: 1px solid #dfe2e7; border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; }
details > summary { cursor: pointer; font-weight: 600; font-size: 16px; }
details.nested { border: 0; border-top: 1px solid #eceef2; border-radius: 0; padding: 8px 0; margin: 0; }
details.nested > summary { font-size: 14px; font-weight: 500; }
details h3 { font-size: 15px; margin: 18px 0 6px; }
details h4 { font-size: 13px; margin: 12px 0 4px; color: #5d6470; }
.scroll { overflow-x: auto; }
table.data td { font-size: 13px; max-width: 420px; overflow-wrap: anywhere; }
table.data tr.target td { background: #eef2ff; font-weight: 600; }
dl.fields { display: grid; grid-template-columns: max-content 1fr; gap: 2px 16px; font-size: 14px; margin: 8px 0; }
dl.fields dt { color: #5d6470; }
dl.fields dd { margin: 0; overflow-wrap: anywhere; }
pre { background: #f5f6f8; padding: 10px; border-radius: 8px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; max-height: 320px; overflow: auto; }
.muted { color: #5d6470; }
.big { font-size: 28px; font-weight: 700; margin: 8px 0; }
a.raw { font-size: 13px; }
.answer { margin: 8px 0; }
.st { font-weight: 600; }
.st-pass, .st-complete, .st-observed { color: #1d7a46; }
.st-warning, .st-partial { color: #a45f00; }
.st-fail, .st-error { color: #b3261e; }
.st-unknown { color: #5d6470; }
```

In `src/companyscan/views/templates/index.html`, change the first line inside the Files `<td>` from

```html
          <a href="{{ (r.dir / 'manifest.json') | file_url }}">manifest</a>
```

to

```html
          <a href="/run/{{ r.dir.name | urlencode }}"><b>Dashboard</b></a>
          <a href="{{ (r.dir / 'manifest.json') | file_url }}">manifest</a>
```

In `README.md`, append this paragraph to the end of the `## Web UI` section, just before the next `## ` heading:

```markdown
Each site's **Dashboard** link (`/run/<bundle>`) shows everything that crawl captured:
- **Cards:** a summary card per area.
- **Sections:** a collapsible section for the report and findings; pages (sortable by clicking a column heading); the technical reports; accessibility; security, fonts and Meta ads; the AI reputation rank, sentiment and buyer answers; social profiles and identity; and coverage limits.

Every section links to its raw JSON. Missing files show as "not collected", and all captured text is displayed escaped.
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_dashboard tests.test_web -v`
Expected: all OK. `test_web` still passes, and `/report` behaves the same through `bundle_path`.

Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`
Expected: all OK.

- [ ] **Step 7: Check against a real bundle**

Run: `PYTHONPATH=src .venv/bin/python -c "from fastapi.testclient import TestClient; from companyscan.web.app import create_app; c = TestClient(create_app('output'), base_url='http://127.0.0.1'); r = c.get('/run/matthewkantor.com-20260923-223624'); print(r.status_code, len(r.text))"`
Expected: `200` and a length in the tens of thousands.
