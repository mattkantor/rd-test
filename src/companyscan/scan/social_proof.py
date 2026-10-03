"""Social proof on the site: reviews and testimonials a buyer can see, and ways for customers to leave a review, a
testimonial or a referral. Read from the captured pages only, with no requests. Heuristic (INFERRED): it says what
the HTML shows, never that the reviews are genuine or current."""
import re

EXAMPLE_MAX, EXAMPLES = 200, 10
PROOF = {"json_ld_reviews", "testimonial_section", "attributed_quote", "review_widget", "rating_text"}
ASK = {"review_link", "testimonial_ask", "referral_ask"}
SECTION = re.compile(r"testimonial|what (?:our )?(?:clients|customers|people) (?:say|are saying)|^reviews?$|kind words|"
                     r"success stories|in their words|client stories|customer stories", re.I)
NEGATED = re.compile(r"\b(?:not|no|never|without)\b", re.I)  # "Investigations, not testimonials."
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


def attributed(lines, i, match, labels=frozenset()):
    """A quote counts as a testimonial when a short name-like line sits right before or after it, on its line or the
    neighbouring one. labels: the page's link texts; a menu item ("Reviews") is never an attribution."""
    line = lines[i]
    near = [line[:match.start()], line[match.end():]] + lines[max(i - 1, 0):i] + lines[i + 1:i + 2]
    return any(0 < len(c.strip()) <= 60 and c.strip().lower() not in labels and NAME.fullmatch(c.strip()) for c in near)


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
    section = next((h for h in heads + short if SECTION.search(h.strip(" .:")) and not NEGATED.search(h)), None)
    if section or (isinstance(p.get("classification"), dict) and p["classification"].get("label") == "testimonial"):
        found.append(("testimonial_section", section or "testimonial page"))
    for i, line in enumerate(lines):
        match = QUOTE.search(line)
        if match and attributed(lines, i, match, labels):
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
