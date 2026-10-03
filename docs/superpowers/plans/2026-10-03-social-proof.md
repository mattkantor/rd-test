# Social Proof Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every crawl checks the site for social proof (reviews and testimonials shown, and ways to leave a review, testimonial or referral), counts Google reviews (none is a failure), notes Trustpilot shown on the site, and carries the result into the dashboard, report, scorecard and fix pack.

**Architecture:** A new stdlib module `scan/social_proof.py` reads the captured pages (no requests) and writes `technical/social-proof.json` beside `aeo` and `social-preview`. The extractor starts recording Trustpilot widget attributes. The dashboard, report rubric, scorecard and fix pack read that file plus the existing `google_business.json`.

**Tech Stack:** Python 3.10+ stdlib, Django/Jinja2 dashboard, markdown rubric.

**Spec:** `docs/superpowers/specs/2026-10-03-social-proof-design.md`

## Global Constraints

- Core scanner stays stdlib-only and same-origin: `social_proof.py` makes no network request, and nothing anywhere requests Trustpilot.
- Signals are heuristics labelled `INFERRED`; examples are quoted from the page, ≤ 200 characters, never presented as proof that reviews are genuine.
- Status values: `PASS` (proof and ask), `WARNING` (one of the two), `FAIL` (neither), `UNKNOWN` (no extracted pages).
- Google: not found, or found with no reviews, counts against social proof.
- All captured text is rendered escaped (dashboard) or through `fixpack.clean()` (fix pack).
- Tests use local fixtures only. Full suite: `.venv/bin/python manage.py test tests --top-level-directory tests`; one module: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest <module>`.
- The user keeps uncommitted edits in `README.md`, `src/companyscan/report/scorecard.py`, `report.css`, `tests/test_scorecard.py`, `docs/marketing.md`. **Stage explicit paths only; never `git commit -a` or `git add -A`.** For a file that also holds user edits, stage only this plan's hunk: apply the same edit to `git show HEAD:<file>`, write it with `git hash-object -w --stdin` and `git update-index --cacheinfo 100644,<sha>,<file>`. Check `git diff --cached --stat` before every commit.

## Review Focus

1. Navigation labels like a "Reviews" menu link must not alone make a page "show proof" when the page has no review content; a heading or short standalone line is required for `testimonial_section`. (Task 1 test: a link text "Reviews" alone is not a section.)
2. A quote with no attribution nearby (an ordinary quoted phrase in prose) must not count as a testimonial. (Task 1 test.)
3. A page whose JSON fields are missing or wrong-shaped (no `visible_text`, links as strings) must not crash the scan. (Task 1 test.)
4. "No Google reviews" must appear only when `google_business` actually ran; a crawl without that dimension says nothing about Google. (Task 2 test.)
5. The fix pack must never fill in a testimonial; with no quotes on the site it leaves a `TODO(owner)`. (Task 4 test.)

---

### Task 1: The on-site check and the extractor

**Files:**
- Create: `src/companyscan/scan/social_proof.py`
- Modify: `src/companyscan/scan/extract.py` (record `trustpilot_widgets`)
- Modify: `src/companyscan/scan/technical.py` (write `social-proof`)
- Create: `tests/test_social_proof.py`
- Modify: `tests/test_companyscan.py:121` (the report list)

**Interfaces:**
- Produces: `social_proof.check(pages) -> dict` with keys `kind`, `status`, `pages_checked`, `has_proof`, `has_ask`, `pages_with_proof` (list of URLs), `signals` ({kind: page count}), `examples` ([{kind, url, example}] ≤ 10), `profiles` ({platform: url}), `trustpilot` ({widget: bool, profile_link, review_link, score_text}), `limitations`. `PROOF`, `ASK` (sets of signal kinds). Pages gain `trustpilot_widgets: [{businessunit_id, template_id, style_height}]`.

- [ ] **Step 1: Write the failing tests** in `tests/test_social_proof.py`:

```python
import unittest

from companyscan.scan import social_proof
from companyscan.scan.extract import extract

QUOTE = "On my call with Matt, we productively addressed a huge range of issues in a single half-hour."


def page(url="https://acme.test/", **fields):
    base = {"url": url, "visible_text": "", "headings": [], "links": [], "script_sources": [], "json_ld": {"types": []},
            "testimonials": [], "quotation_candidates": [], "classification": {"label": "other"}, "trustpilot_widgets": []}
    return {**base, **fields}


class SocialProofTest(unittest.TestCase):
    def kinds(self, result):
        return set(result["signals"])

    def test_quotes_like_a_real_site_are_proof(self):
        result = social_proof.check([page(visible_text=f"In their words.\nChris, SaaS founder“{QUOTE}”")])
        self.assertEqual(self.kinds(result), {"testimonial_section", "attributed_quote"})
        self.assertEqual((result["has_proof"], result["has_ask"], result["status"]), (True, False, "WARNING"))
        self.assertEqual(result["pages_with_proof"], ["https://acme.test/"])

    def test_asks_for_reviews_and_referrals(self):
        result = social_proof.check([page(
            links=[{"url": "https://search.google.com/local/writereview?placeid=X1", "text": "Review us on Google"},
                   {"url": "https://acme.test/contact", "text": "Share your experience"}],
            visible_text="Know someone who needs us? Refer a friend and you both save.")])
        self.assertEqual(self.kinds(result), {"review_link", "testimonial_ask", "referral_ask"})
        self.assertEqual((result["has_proof"], result["has_ask"], result["status"]), (False, True, "WARNING"))

    def test_both_pass_and_neither_fails(self):
        both = page(json_ld={"types": ["Review"]}, links=[{"url": "https://acme.test/review", "text": "Leave a review"}])
        self.assertEqual(social_proof.check([both])["status"], "PASS")
        self.assertEqual(social_proof.check([page(visible_text="We build websites.")])["status"], "FAIL")
        self.assertEqual(social_proof.check([])["status"], "UNKNOWN")

    def test_nav_labels_and_unattributed_quotes_are_not_proof(self):
        result = social_proof.check([page(
            links=[{"url": "https://acme.test/reviews", "text": "Reviews"}],  # A menu label, also in the page text.
            visible_text=f'Home\nReviews\nAs the saying goes, "{QUOTE}" That is how we think about planning.')])
        self.assertFalse(result["has_proof"])

    def test_widgets_and_trustpilot_on_the_site(self):
        result = social_proof.check([page(
            script_sources=["https://widget.trustpilot.com/bootstrap/v5/tp.widget.bootstrap.min.js"],
            links=[{"url": "https://www.trustpilot.com/review/acme.test", "text": "See our reviews"}],
            visible_text="Rated 4.8 out of 5 on Trustpilot from 1,203 reviews.\nWe're also on Trustpilot.")])
        self.assertEqual(result["trustpilot"], {"widget": True, "profile_link": "https://www.trustpilot.com/review/acme.test",
                                                "review_link": None, "score_text": "Rated 4.8 out of 5 on Trustpilot from 1,203 reviews"})
        self.assertIn("review_widget", self.kinds(result))
        self.assertIn("rating_text", self.kinds(result))
        self.assertEqual(result["profiles"], {"Trustpilot": "https://www.trustpilot.com/review/acme.test"})
        bare = social_proof.check([page(visible_text="We're on Trustpilot.")])
        self.assertIsNone(bare["trustpilot"]["score_text"])  # Names Trustpilot but holds no rating.

    def test_examples_are_short_and_few(self):
        long_quote = "word " * 100
        pages = [page(url=f"https://acme.test/{i}", visible_text=f"Jane Doe, CEO“{long_quote}”") for i in range(15)]
        result = social_proof.check(pages)
        self.assertEqual(len(result["examples"]), social_proof.EXAMPLES)
        self.assertTrue(all(len(e["example"]) <= social_proof.EXAMPLE_MAX for e in result["examples"]))

    def test_wrong_shaped_pages_dont_crash(self):
        result = social_proof.check([{"url": "https://acme.test/"}, {"url": "x", "visible_text": None, "links": ["bad"],
                                                                     "headings": "h", "json_ld": []}])
        self.assertEqual(result["status"], "FAIL")

    def test_extractor_records_trustpilot_widgets(self):
        html = ('<html><body><div class="trustpilot-widget" data-businessunit-id="5419b6a8" '
                'data-template-id="t1" data-style-height="24px"></div></body></html>')
        self.assertEqual(extract(html, "https://acme.test/")["trustpilot_widgets"],
                         [{"businessunit_id": "5419b6a8", "template_id": "t1", "style_height": "24px"}])
        result = social_proof.check([page(trustpilot_widgets=[{"businessunit_id": "5419b6a8"}])])
        self.assertTrue(result["trustpilot"]["widget"])
```

In `tests/test_companyscan.py`, change the report list on line 121 to:

```python
            for report in ("measurement", "aeo", "social-preview", "social-proof"):
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest test_social_proof`
Expected: ERROR `ImportError: cannot import name 'social_proof'`.

- [ ] **Step 3: Implement** `src/companyscan/scan/social_proof.py`:

```python
"""Social proof on the site: reviews and testimonials a buyer can see, and ways for customers to leave a review, a
testimonial or a referral. Read from the captured pages only, with no requests. Heuristic (INFERRED): it says what
the HTML shows, never that the reviews are genuine or current."""
import re

EXAMPLE_MAX, EXAMPLES = 200, 10
PROOF = {"json_ld_reviews", "testimonial_section", "attributed_quote", "review_widget", "rating_text"}
ASK = {"review_link", "testimonial_ask", "referral_ask"}
SECTION = re.compile(r"testimonial|what (?:our )?(?:clients|customers|people) (?:say|are saying)|^reviews?$|kind words|"
                     r"success stories|in their words|client stories|customer stories", re.I)
QUOTE = re.compile(r"[“\"]([^”\"]{40,})[”\"]")
# "Chris, SaaS founder" or "— Jane Doe": a capitalised name of up to four words, optionally a role after a comma.
NAME = re.compile(r"[—–-]?\s*[A-Z][\w.'’-]+(?: [A-Z][\w.'’-]+){0,3}(?:\s*,\s*[^,\n“”\"]{2,40})?")
WIDGETS = [("Trustpilot", r"widget\.trustpilot\.com"), ("Elfsight", r"elfsight(?:cdn)?\.com"), ("Birdeye", r"birdeye\.com"),
           ("Podium", r"podium\.com"), ("Yotpo", r"yotpo\.com"), ("Reviews.io", r"reviews\.(?:io|co\.uk)"),
           ("Judge.me", r"judge\.me"), ("Stamped", r"stamped\.io"), ("Okendo", r"okendo\.io"),
           ("EmbedSocial", r"embedsocial\.com"), ("Featurable", r"featurable\.com"), ("Yelp", r"yelp\.com/embed"),
           ("G2", r"g2\.com/(?:widgets|products/[^/]+/widget)|g2crowd"), ("Capterra", r"capterra\.com/(?:widgets|badge)"),
           ("Clutch", r"widget\.clutch\.co")]
REVIEW_HREF = re.compile(r"search\.google\.com/local/writereview|g\.page/r/[^/]+/review|trustpilot\.com/evaluate/|"
                         r"yelp\.[a-z.]+/writeareview|g2\.com/products/[^/]+/(?:reviews/new|take_survey)|"
                         r"clutch\.co/profile/[^/]+/review|capterra\.com/reviews/new", re.I)
REVIEW_TEXT = re.compile(r"\b(?:leave|write|post|submit|add)\s+(?:us\s+)?a\s+review\b|\breview us\b|\brate us\b", re.I)
TESTIMONIAL_ASK = re.compile(r"share your (?:experience|story|feedback)|submit (?:a |your )?testimonial|tell us how we did|"
                             r"leave (?:us )?(?:a |your )?(?:testimonial|feedback)", re.I)
REFERRAL = re.compile(r"\brefer (?:a |your )?(?:friend|colleague|client|business)\b|\breferral(?:s| program| scheme)?\b", re.I)
PROFILES = [("Google", r"google\.[a-z.]+/maps/place|maps\.app\.goo\.gl|g\.page/(?!r/)"), ("Trustpilot", r"trustpilot\.com/review/"),
            ("Yelp", r"yelp\.[a-z.]+/biz/"), ("G2", r"g2\.com/products/[^/]+/reviews?$"), ("Capterra", r"capterra\.com/p/"),
            ("Clutch", r"clutch\.co/profile/[^/]+$")]
RATING = re.compile(r"\b\d(?:\.\d)?\s*(?:/\s*5|out of 5|stars?)\b|trustscore|\b\d[\d,]*\s+reviews\b|\brated\b", re.I)
LIMITATIONS = ["HTML only: widgets that load reviews with JavaScript are seen as widgets; the reviews they show are not read.",
               "Heuristic: section headings, attributed quotes and asks are matched by pattern and may miss or over-match.",
               "Nothing is fetched from review platforms; Google reviews come from the google_business check."]


def clip(text):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= EXAMPLE_MAX else s[:EXAMPLE_MAX - 1] + "…"


def rows(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def attributed(lines, i, match):
    """A quote counts as a testimonial when a short name-like line sits right before or after it, on its line or the
    neighbouring one."""
    line = lines[i]
    near = [line[:match.start()], line[match.end():]] + lines[max(i - 1, 0):i] + lines[i + 1:i + 2]
    return any(0 < len(c.strip()) <= 60 and NAME.fullmatch(c.strip()) for c in near)


def signals(p):
    """[(kind, example)] found on one page."""
    found = []
    text = p.get("visible_text") if isinstance(p.get("visible_text"), str) else ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    links = rows(p.get("links"))
    types = obj_types(p)
    if {"Review", "AggregateRating"} & types or rows(p.get("testimonials")):
        found.append(("json_ld_reviews", "JSON-LD " + ", ".join(sorted({"Review", "AggregateRating"} & types) or ["Review"])))
    heads = [h.get("text") for h in rows(p.get("headings")) if isinstance(h.get("text"), str)]
    labels = {str(l.get("text") or "").strip().lower() for l in links}  # Menu text also appears in visible_text.
    short = [l for l in lines if len(l) <= 40 and l.lower() not in labels]
    section = next((h for h in heads + short if SECTION.search(h.strip(" .:"))), None)
    if section or (isinstance(p.get("classification"), dict) and p["classification"].get("label") == "testimonial"):
        found.append(("testimonial_section", section or "testimonial page"))
    for i, line in enumerate(lines):
        match = QUOTE.search(line)
        if match and attributed(lines, i, match):
            found.append(("attributed_quote", line))
            break
    for q in rows(p.get("quotation_candidates")):
        if q.get("cite") or NAME.fullmatch(str(q.get("text") or "").split("\n")[-1].strip()):
            found.append(("attributed_quote", q.get("text")))
            break
    sources = [s for s in p.get("script_sources") or [] if isinstance(s, str)]
    for name, pattern in WIDGETS:
        if any(re.search(pattern, s, re.I) for s in sources):
            found.append(("review_widget", name))
    if rows(p.get("trustpilot_widgets")) and not any(n == "Trustpilot" for k, n in found if k == "review_widget"):
        found.append(("review_widget", "Trustpilot"))
    rating = next((s for line in lines for s in re.split(r"(?<=[.!?])\s+", line)
                   if "trustpilot" in s.lower() and RATING.search(s)), None)
    if rating:
        found.append(("rating_text", rating.rstrip(".")))
    for link in links:
        url, label = str(link.get("url") or ""), str(link.get("text") or "")
        if REVIEW_HREF.search(url) or REVIEW_TEXT.search(label):
            found.append(("review_link", label or url))
        if TESTIMONIAL_ASK.search(label):
            found.append(("testimonial_ask", label))
    asks = [label for label in (str(l.get("text") or "") for l in links)] + lines
    referral = next((s for s in asks if REFERRAL.search(s)), None)
    if referral:
        found.append(("referral_ask", referral))
    return found


def obj_types(p):
    ld = p.get("json_ld") if isinstance(p.get("json_ld"), dict) else {}
    return {t for t in ld.get("types") or [] if isinstance(t, str)}


def check(pages):
    """technical/social-proof.json: what proof the site shows and how it asks for more."""
    pages = [p for p in pages if isinstance(p, dict) and isinstance(p.get("url"), str)]
    counts, examples, proof_pages, profiles = {}, [], [], {}
    trustpilot = {"widget": False, "profile_link": None, "review_link": None, "score_text": None}
    for p in pages:
        found = signals(p)
        for kind in {k for k, _ in found}:
            counts[kind] = counts.get(kind, 0) + 1
        if {k for k, _ in found} & PROOF:
            proof_pages.append(p["url"])
        seen = set()
        for kind, example in found:
            if kind not in seen and len(examples) < EXAMPLES:
                examples.append({"kind": kind, "url": p["url"], "example": clip(example)})
            seen.add(kind)
            if kind == "review_widget" and example == "Trustpilot":
                trustpilot["widget"] = True
            if kind == "rating_text" and not trustpilot["score_text"]:
                trustpilot["score_text"] = clip(example)
        for link in rows(p.get("links")):
            url = str(link.get("url") or "")
            for name, pattern in PROFILES:
                if re.search(pattern, url, re.I):
                    profiles.setdefault(name, url)
            if "trustpilot.com/evaluate/" in url.lower() and not trustpilot["review_link"]:
                trustpilot["review_link"] = url
    trustpilot["profile_link"] = profiles.get("Trustpilot")
    has_proof, has_ask = bool(set(counts) & PROOF), bool(set(counts) & ASK)
    status = "UNKNOWN" if not pages else "PASS" if has_proof and has_ask else "WARNING" if has_proof or has_ask else "FAIL"
    return {"kind": "INFERRED", "status": status, "pages_checked": len(pages), "has_proof": has_proof, "has_ask": has_ask,
            "pages_with_proof": proof_pages, "signals": counts, "examples": examples, "profiles": profiles,
            "trustpilot": trustpilot, "limitations": LIMITATIONS}
```

In `extract.py` `Parser.__init__`, add `self.trustpilot = []` after `self.hidden = 0`. In `handle_starttag`, after the `iframe` branch:

```python
        if "trustpilot-widget" in (attrs.get("class") or "").split():
            self.trustpilot.append({k.replace("-", "_"): attrs.get(f"data-{k}") for k in ("businessunit-id", "template-id", "style-height")})
```

In `extract()`'s returned dict, after `"measurement": detect(...)`, add:

```python
            "trustpilot_widgets": p.trustpilot,
```

In `technical.py`, add `from .social_proof import check as social_proof` with the other imports, and in `reports()`'s returned dict, after `"social-preview": social_preview(pages)`, add `, "social-proof": social_proof(pages)` (keep it one dict literal).

- [ ] **Step 4: Run tests**

Run: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest test_social_proof test_companyscan`
Expected: all PASS. Then the full suite → OK.

- [ ] **Step 5: Commit**

```bash
git add src/companyscan/scan/social_proof.py src/companyscan/scan/extract.py src/companyscan/scan/technical.py tests/test_social_proof.py tests/test_companyscan.py
git diff --cached --stat   # only these five
git commit -m "Check every crawl for social proof shown and asked for"
```

---

### Task 2: Dashboard

**Files:**
- Modify: `src/companyscan/web/dashboard.py` (`PER_PAGE`, `METRICS`, `metrics()`, `tiles()`, `facts()`, `attention()`, `site_cards()`)
- Test: `tests/test_dashboard.py` (`LoadTest`)

**Interfaces:**
- Consumes: `technical/social-proof.json` (Task 1), `technical/google_business.json` (existing).
- Produces: `google_reviews(raw) -> (text, bad) | None`; metric `proof_pages`; tile "Social proof" (`key="proof_pages"`, `href="#site"`); facts "Reviews on site", "Review or referral link"; site card "Social proof".

- [ ] **Step 1: Write the failing tests** in `LoadTest`:

```python
    def proof(self, **summary):
        write(self.bundle, "technical/social-proof.json", {"kind": "INFERRED", "status": "WARNING", "pages_checked": 3,
            "has_proof": True, "has_ask": False, "pages_with_proof": ["https://acme.test/"],
            "signals": {"attributed_quote": 1}, "profiles": {},
            "examples": [{"kind": "attributed_quote", "url": "https://acme.test/", "example": "<b>Chris</b>, founder “Great”"}],
            "trustpilot": {"widget": True, "profile_link": None, "review_link": None, "score_text": None}, **summary})

    def test_social_proof_tile_facts_card_and_anomalies(self):
        self.proof()
        m = load(self.bundle)
        tile = {t["title"]: t for t in m["tiles"]}["Social proof"]
        self.assertEqual((tile["value"], tile["status"], tile["key"]), (1, "Shown, never asked", "proof_pages"))
        self.assertIn("Trustpilot widget", tile["sub"])
        self.assertNotIn("Google", tile["sub"])  # google_business didn't run in this crawl: nothing said about Google.
        self.assertEqual(m["metrics"]["proof_pages"], 1)
        facts = {label: value for label, value, _, _ in m["facts"]}
        self.assertEqual((facts["Reviews on site"], facts["Review or referral link"]), (True, False))
        self.assertIn(("warning", "No way for customers to leave a review, testimonial or referral"),
                      [(a["level"], a["text"]) for a in m["attention"]])
        card = next(c for c in m["site"] if c["title"] == "Social proof")
        self.assertEqual(card["file"], "technical/social-proof.json")

    def test_no_google_reviews_counts_against_social_proof(self):
        self.proof(status="FAIL", has_proof=False, pages_with_proof=[])
        write(self.bundle, "technical/google_business.json", {"status": "OBSERVED", "found": False})
        m = load(self.bundle)
        tile = {t["title"]: t for t in m["tiles"]}["Social proof"]
        self.assertIn("No Google reviews", tile["sub"])
        self.assertEqual(tile["level"], "critical")
        texts = [(a["level"], a["text"]) for a in m["attention"]]
        self.assertIn(("serious", "No reviews or testimonials on the site, and no way to leave one"), texts)
        self.assertIn(("serious", "No Google Business Profile: buyers who check Google see no reviews"), texts)
        write(self.bundle, "technical/google_business.json", {"status": "OBSERVED", "found": True, "reviews": {"rating": 4.8, "count": 84}})
        self.assertIn("Google 4.8★ (84)", {t["title"]: t for t in load(self.bundle)["tiles"]}["Social proof"]["sub"])
```

Also add `"Social proof"` is escaped when rendered: in `DashboardPageTest`, add:

```python
    def test_renders_social_proof_examples_escaped(self):
        d = full_bundle(self.root)
        write(d, "technical/social-proof.json", {"status": "WARNING", "has_proof": True, "has_ask": False, "pages_checked": 1,
                                                 "pages_with_proof": [], "signals": {}, "profiles": {}, "trustpilot": {},
                                                 "examples": [{"kind": "attributed_quote", "url": "https://acme.test/", "example": "<b>Chris</b>"}]})
        page = self.client.get("/run/acme").text
        self.assertIn("&lt;b&gt;Chris&lt;/b&gt;", page)
        self.assertNotIn("<b>Chris</b>", page)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest test_dashboard.LoadTest`
Expected: FAIL/ERROR (`KeyError: 'Social proof'`).

- [ ] **Step 3: Implement** in `dashboard.py`:

`PER_PAGE`: add `"social-proof"` after `"social-preview"`.

`METRICS`: after `"social_issues"` add `"proof_pages": ("Pages with social proof", True, str),`.

In `metrics()`, after the `social-preview` block:

```python
    t = raw["social-proof"]
    if isinstance(t, dict) and t.get("status") in ("PASS", "WARNING", "FAIL"):
        put("proof_pages", len(as_list(t.get("pages_with_proof"))))
```

Add after `facts()`'s definition site (before `tiles()`), a helper:

```python
PROOF_STATUS = {"PASS": ("good", "Shown and asked"), "FAIL": ("critical", "None found")}


def google_reviews(raw):
    """(text, bad) for Google's part of social proof, or None when google_business didn't run. No listing, or a listing
    with no reviews, is bad: buyers who check Google see nothing."""
    g = raw["google_business"]
    if not isinstance(g, dict) or g.get("status") == "UNKNOWN":
        return None
    reviews = as_dict(g.get("reviews"))
    count, rating = num(reviews.get("count")), num(reviews.get("rating"))
    if not g.get("found") or not count:
        return "No Google reviews", True
    return (f"Google {rating}★ ({count})" if rating is not None else f"Google ({count})"), False
```

In `tiles()`, before the `v = model["metrics"]` line:

```python
    t = raw["social-proof"]
    if isinstance(t, dict) and t.get("status") in ("PASS", "WARNING", "FAIL"):
        level, status = PROOF_STATUS.get(t["status"], ("warning", "Shown, never asked" if t.get("has_proof") else "Asked, never shown"))
        google = google_reviews(raw)
        parts = ["pages show reviews or testimonials"] + ([google[0]] if google else []) + \
            (["Trustpilot widget"] if as_dict(t.get("trustpilot")).get("widget") else [])
        if google and google[1] and level != "critical":
            level = "serious"
        out.append(tile("Social proof", "#site", len(as_list(t.get("pages_with_proof"))), " · ".join(parts), level, status,
                        key="proof_pages"))
```

In `facts()`, add two rows to the returned list, after "Ad pixel":

```python
            ("Reviews on site", yes(sp.get("has_proof")) if sp else None, "#site", ""),
            ("Review or referral link", yes(sp.get("has_ask")) if sp else None, "#site", ""),
```

with `sp = raw["social-proof"] if isinstance(raw["social-proof"], dict) and raw["social-proof"].get("status") != "UNKNOWN" else None` near the top of `facts()`.

In `attention()`, replace the Google block:

```python
    t = raw["google_business"]
    if isinstance(t, dict) and t.get("status") == "OBSERVED":
        if t.get("found") is False:
            add("warning", "No Google Business Profile matched this site", "#listing")
```

with:

```python
    t = raw["google_business"]
    if isinstance(t, dict) and t.get("status") == "OBSERVED":
        if t.get("found") is False:
            add("serious", "No Google Business Profile: buyers who check Google see no reviews", "#listing")
        elif not num(as_dict(t.get("reviews")).get("count")):
            add("serious", "The Google listing has no reviews", "#listing")
```

and after it add:

```python
    t = raw["social-proof"]
    if isinstance(t, dict) and t.get("status") in ("WARNING", "FAIL"):
        if not t.get("has_proof") and not t.get("has_ask"):
            add("serious", "No reviews or testimonials on the site, and no way to leave one", "#site")
        elif not t.get("has_proof"):
            add("serious", "No reviews or testimonials shown on the site", "#site")
        else:
            add("warning", "No way for customers to leave a review, testimonial or referral", "#site")
```

In `site_cards()`, before `return cards`:

```python
    t = raw["social-proof"]
    if isinstance(t, dict) and t.get("status") in ("PASS", "WARNING", "FAIL"):
        level, status = PROOF_STATUS.get(t["status"], ("warning", "Shown, never asked" if t.get("has_proof") else "Asked, never shown"))
        tp = as_dict(t.get("trustpilot"))
        trustpilot = ", ".join(n for n, on in (("widget", tp.get("widget")), ("profile link", tp.get("profile_link")),
                                               ("score shown", tp.get("score_text"))) if on) or "not on the site"
        cards.append(info("Social proof", level, status,
                          [("Pages with proof", len(as_list(t.get("pages_with_proof")))),
                           ("Asks for reviews or referrals", "yes" if t.get("has_ask") else "no"),
                           ("Trustpilot", trustpilot), ("Review profiles linked", ", ".join(as_dict(t.get("profiles"))) or "none")],
                          table_label="What was found",
                          rows=[{"what": e.get("kind"), "page": e.get("url"), "example": e.get("example")}
                                for e in as_list(t.get("examples")) if isinstance(e, dict)],
                          note=" ".join(str(x) for x in as_list(t.get("limitations"))), file="technical/social-proof.json"))
    else:
        cards.append(missing_card("Social proof", t, "technical/social-proof.json"))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python manage.py test tests --top-level-directory tests`
Expected: all PASS. If an existing assertion names "No Google Business Profile matched this site" or lists the facts row's labels exactly, update it to the new wording/labels (the behaviour change is intended by the spec).

- [ ] **Step 5: Commit**

```bash
git add src/companyscan/web/dashboard.py tests/test_dashboard.py
git commit -m "Show social proof on the dashboard and count missing Google reviews against it"
```

---

### Task 3: Report rubric and scorecard

**Files:**
- Create: `src/companyscan/skills/footprint-analyze/references/social_proof.md`
- Modify: `src/companyscan/skills/footprint-analyze/SKILL.md` (new step 7c)
- Modify: `src/companyscan/report/scorecard.py` (`WHY["social_proof"]`, `LABELS["social_proof"]`; hunk-only staging)
- Test: `tests/test_social_proof.py`

**Interfaces:**
- Produces: analysis area key `social_proof` (findings `P` prefix); `scorecard.WHY["social_proof"]`, `scorecard.LABELS["social_proof"]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_social_proof.py`):

```python
class SocialProofReportTest(unittest.TestCase):
    def test_rubric_is_shipped_and_named_in_the_skill(self):
        from pathlib import Path
        from companyscan.report.analyze import SKILL, rubrics
        self.assertIn("social_proof.md", SKILL.read_text())
        self.assertTrue((SKILL.parent / "references/social_proof.md").exists())
        self.assertIn("# references/social_proof.md", rubrics(Path("/nonexistent")))  # Always applies.

    def test_scorecard_explains_social_proof(self):
        from companyscan.report import scorecard
        self.assertIn("Buyers trust other customers", scorecard.WHY["social_proof"])
        self.assertEqual(scorecard.LABELS["social_proof"], "Social proof")
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest test_social_proof.SocialProofReportTest`
Expected: FAIL (`social_proof.md` not in SKILL; `KeyError: 'social_proof'`).

- [ ] **Step 3: Implement.** Create `references/social_proof.md`:

```markdown
# Social proof

Whether a buyer who reaches the site sees that other customers chose this business, and whether happy customers are
asked to say so. Use the same verdicts and citation shape as [analysis-rubric.md](analysis-rubric.md), and give every
finding a `business_impact` per [business-impact.md](business-impact.md) (loss type usually `trust` or `conversions`).
Finding IDs use a `P` prefix. Put the area in `analysis.json` as `social_proof` with `verdict`, `summary` and
`findings`.

Sources: `technical/social-proof.json` (always present; signals, quoted `examples`, `profiles`, `trustpilot`), the
per-page `visible_text` to confirm examples, and `technical/google_business.json` when present.

- **On-site proof** (`has_proof`): reviews or testimonials a buyer can see. Confirm the quoted examples against the
  page; reject false matches (a quoted phrase in an article, a "Reviews" menu label). Proof on the homepage or the main
  service/pricing page matters most; proof only on a deep page is weak.
- **Asks** (`has_ask`): a link or prompt to leave a review, share a testimonial or refer someone.
- **Google**: `google_business.json` with `found: false`, or found with no reviews, means a buyer who checks Google sees
  no reviews. When the file is absent, Google wasn't checked: say so and don't judge it.
- **Trustpilot**: only what the site shows (`trustpilot.widget`, `profile_link`, `score_text`). Nothing was fetched
  from Trustpilot; never state a TrustScore except as quoted from the page.

Verdict:
- `PASS`: real proof on the homepage or a core page, an ask somewhere a customer will see it, and Google reviews when
  Google was checked.
- `WARNING`: proof but no ask; an ask but no proof; proof only on deep pages; or the site is fine but Google has no
  reviews.
- `FAIL`: no reviews or testimonials anywhere on the site and no ask, or no on-site proof with no Google reviews.

Recommend the smallest fixes that matter: show two or three real, attributed quotes on the homepage and the main
service page; add a "Leave us a Google review" link (from the Google Business Profile); add a referral prompt on the
contact page. Never suggest inventing testimonials or adding review markup without real reviews.
```

In `SKILL.md`, after the step 7 paragraph (the line starting `7. Check measurement, AEO structured data`), add:

```markdown
7c. Check social proof using [social_proof.md](references/social_proof.md): whether reviews or testimonials are shown on the site, whether customers are asked for reviews, testimonials or referrals, and whether Google shows reviews. `technical/social-proof.json` is always present. Findings use `P` IDs.
```

In `scorecard.py`, insert before the `WHY_DEFAULT = ` line, in **both** the working tree and the staged `HEAD` version (the line exists in both):

```python
WHY["social_proof"] = ("Buyers trust other customers more than anything you say about yourself. Reviews and testimonials "
                       "where they decide, and an easy way for happy customers to leave one, are what tip them your way.")
LABELS["social_proof"] = "Social proof"
```

Stage only that hunk:

```bash
python3 - <<'PY'
import subprocess
from pathlib import Path
path, anchor = "src/companyscan/report/scorecard.py", "WHY_DEFAULT = "
add = ('WHY["social_proof"] = ("Buyers trust other customers more than anything you say about yourself. Reviews and testimonials "\n'
       '                       "where they decide, and an easy way for happy customers to leave one, are what tip them your way.")\n'
       'LABELS["social_proof"] = "Social proof"\n')
def put(text):
    assert text.count(anchor) == 1 and 'WHY["social_proof"]' not in text
    return text.replace(anchor, add + anchor)
Path(path).write_text(put(Path(path).read_text()))
head = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, text=True, check=True).stdout
sha = subprocess.run(["git", "hash-object", "-w", "--stdin"], input=put(head), capture_output=True, text=True, check=True).stdout.strip()
subprocess.run(["git", "update-index", "--cacheinfo", f"100644,{sha},{path}"], check=True)
PY
```

**Trust stage:** `STAGES` exists only in the user's uncommitted scorecard work. In the working tree only (do not stage), add `"social_proof"` first in the Trust tuple: `("social_proof", "practitioners", "fonts", "security")`. Report this to the user as riding with their pending scorecard change.

- [ ] **Step 4: Run tests**

Run: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest test_social_proof` → PASS; full suite → OK.

- [ ] **Step 5: Commit** (scorecard hunk already staged by the script above)

```bash
git add src/companyscan/skills/footprint-analyze/references/social_proof.md src/companyscan/skills/footprint-analyze/SKILL.md tests/test_social_proof.py
git diff --cached --stat   # scorecard.py shows +3 lines only
git commit -m "Judge social proof in the report and explain it on the scorecard"
```

---

### Task 4: Fix pack task and owner to-do

**Files:**
- Modify: `src/companyscan/report/fixpack.py` (builder `social_proof`, `BUILDERS`, `owner()`)
- Test: `tests/test_fixpack.py`

**Interfaces:**
- Consumes: `Run.tech("social-proof")`, `Run.tech("google_business")`, `task()`, `clean()`, `code()`, `obj()` (existing).
- Produces: task slug `social-proof`, data file `data/social-proof.json` (the attributed quotes found).

- [ ] **Step 1: Write the failing tests** in `FixPackTest`:

```python
    def test_social_proof_task_asks_without_inventing(self):
        d = site(self.root)
        put(d, "technical/social-proof.json", {"status": "FAIL", "has_proof": False, "has_ask": False, "examples": [],
                                               "trustpilot": {"profile_link": None}})
        put(d, "technical/google_business.json", {"status": "OBSERVED", "found": False})
        files = fixpack.build(d)
        name = next(n for n in files if n.endswith("-social-proof.md"))
        text = files[name]
        self.assertIn("No reviews or testimonials", text)
        self.assertIn("No Google reviews", text)
        self.assertIn("TODO(owner): two or three real customer quotes", text)
        self.assertIn("TODO(owner): Google review link", text)
        self.assertIn("Don't invent testimonials", text)
        self.assertIn("ask your last ten customers for a review", files["OWNER-TODO.md"])

    def test_social_proof_task_reuses_quotes_and_the_google_place(self):
        d = site(self.root)
        put(d, "technical/social-proof.json", {"status": "WARNING", "has_proof": True, "has_ask": False,
            "examples": [{"kind": "attributed_quote", "url": "https://acme.test/about", "example": "Chris, founder “Great call”"}],
            "trustpilot": {"profile_link": "https://www.trustpilot.com/review/acme.test"}})
        put(d, "technical/google_business.json", {"status": "OBSERVED", "found": True, "listing": {"place_id": "ChIJ123"},
                                                  "reviews": {"rating": 4.9, "count": 12}})
        files = fixpack.build(d)
        text = next(t for n, t in files.items() if n.endswith("-social-proof.md"))
        self.assertIn("`https://search.google.com/local/writereview?placeid=ChIJ123`", text)
        self.assertIn("`https://www.trustpilot.com/evaluate/acme.test`", text)
        self.assertEqual(json.loads(files["data/social-proof.json"])[0]["example"], "Chris, founder “Great call”")
        self.assertNotIn("No Google reviews", text)

    def test_no_social_proof_task_when_shown_asked_and_reviewed(self):
        d = site(self.root)
        put(d, "technical/social-proof.json", {"status": "PASS", "has_proof": True, "has_ask": True, "examples": []})
        put(d, "technical/google_business.json", {"status": "OBSERVED", "found": True, "reviews": {"count": 3}})
        self.assertNotIn("social-proof", self.tasks(fixpack.build(d)))
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest test_fixpack`
Expected: the first two FAIL with `StopIteration`.

- [ ] **Step 3: Implement** in `fixpack.py`, after `accessibility()`:

```python
def no_google_reviews(run):
    """Why Google shows no reviews, or None (none missing, or google_business didn't run)."""
    g = run.tech("google_business")
    if g is None:
        return None
    count = obj(g.get("reviews")).get("count")
    if not g.get("found"):
        return "no Google Business Profile was found"
    return None if isinstance(count, (int, float)) and count > 0 else "the Google listing has no reviews"


def social_proof(run):
    sp, google = run.tech("social-proof"), no_google_reviews(run)
    wrong = []
    if sp is not None and not sp.get("has_proof"):
        wrong.append("- No reviews or testimonials are shown anywhere on the site.")
    if sp is not None and not sp.get("has_ask"):
        wrong.append("- Nothing asks customers for a review, a testimonial or a referral.")
    if google:
        wrong.append(f"- No Google reviews: {google}.")
    quotes = [{"url": clean(e.get("url")), "example": clean(e.get("example"))}
              for e in items(obj(sp).get("examples")) if e.get("kind") == "attributed_quote"]
    place = obj(obj(run.tech("google_business")).get("listing")).get("place_id")
    profile = str(obj(obj(sp).get("trustpilot")).get("profile_link") or "")
    tp_domain = profile.rstrip("/").rsplit("/review/", 1)[-1] if "/review/" in profile else ""
    do = ["Add a short testimonials section to the homepage and to the main services or pricing page. "
          + ("Use the attributed quotes already on the site (`data/social-proof.json`), word for word with their attribution."
             if quotes else "There are none on the site: write `TODO(owner): two or three real customer quotes with "
                            "name and role` there and add it to OWNER-TODO.md."),
          "Add a \"Leave us a Google review\" link to the footer and the contact page: "
          + (f"`https://search.google.com/local/writereview?placeid={clean(place)}`." if place else
             "write `TODO(owner): Google review link (Google Business Profile → Ask for reviews)` and add it to OWNER-TODO.md."),
          "Add a referral prompt (for example \"Know someone who'd benefit? Introduce us.\") and a \"Share your "
          "experience\" link on the contact page and any thank-you page."]
    if tp_domain:
        do.insert(2, f"Link \"Review us on Trustpilot\" to `https://www.trustpilot.com/evaluate/{clean(tp_domain)}`.")
    return task("social-proof", "Show and ask for social proof", "social_proof", run.findings(["social_proof"]), wrong, do,
                ["The homepage and the main services or pricing page each show at least one real, attributed testimonial, "
                 "or a TODO(owner).",
                 "A review link and a referral or share-your-experience prompt appear in the footer or on the contact page."],
                ["Don't invent testimonials, names, roles, ratings or review counts.",
                 "Don't add `Review` or `AggregateRating` JSON-LD unless the reviews are real and shown on that page."],
                quotes or None)
```

Add `social_proof` to `BUILDERS` after `accessibility`:

```python
BUILDERS = (analytics, security, seo, structured_data, social, accessibility, social_proof, questions, slop, persuasion,
            practitioners)
```

In `owner()`, after the loop over `OFF_SITE`, before the return:

```python
    google = no_google_reviews(run)
    if google:
        off.append(f"- **Google Business Profile**: {google}. Claim or create the listing, then ask your last ten "
                   "customers for a review.")
```

- [ ] **Step 4: Run tests**

Run: `cd tests && PYTHONPATH=../src ../.venv/bin/python -m unittest test_fixpack` → PASS; full suite → OK.

- [ ] **Step 5: Commit**

```bash
git add src/companyscan/report/fixpack.py tests/test_fixpack.py
git commit -m "Add a social proof task to the fix pack"
```

---

### Task 5: Docs

**Files:**
- Modify: `docs/output-schema.md`, `README.md` (hunk-only staging)

- [ ] **Step 1:** In `docs/output-schema.md`, beside the `technical/social-preview.json` entry, add `technical/social-proof.json` with its fields (`status`, `has_proof`, `has_ask`, `pages_with_proof`, `signals`, `examples`, `profiles`, `trustpilot`, `limitations`), and under `pages/*.json` add `trustpilot_widgets` (`businessunit_id`, `template_id`, `style_height`).

- [ ] **Step 2:** In `README.md`, in "How it works" step 2 ("Technical reports."), add "social proof" to the list of always-written reports, and add one paragraph after the Fix pack section:

```markdown
### Social proof

Every crawl writes `technical/social-proof.json`: whether the site shows reviews or testimonials (JSON-LD reviews, a testimonials section, attributed quotes, review widgets, a Trustpilot score printed on the page) and whether it asks customers for a review, a testimonial or a referral (review links including Google's write-review link, "share your experience", "refer a friend"). Both is `PASS`, one is `WARNING`, neither is `FAIL`. Trustpilot is only what the site shows (its widget, a link to the profile, a printed score); nothing is requested from Trustpilot. Google reviews come from `google_business`: no listing, or a listing without reviews, counts against social proof. The dashboard shows a **Social proof** tile and card, the report judges it with `references/social_proof.md`, it sits in the scorecard's Trust stage, and the fix pack gets a "Show and ask for social proof" task that never invents testimonials.
```

Stage the README hunk only (apply both edits to `git show HEAD:README.md` and `update-index`, as in Task 3).

- [ ] **Step 3: Commit**

```bash
git add docs/output-schema.md
git diff --cached --stat   # README.md and output-schema.md only
git commit -m "Document the social proof check"
```
