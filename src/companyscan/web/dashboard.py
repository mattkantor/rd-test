"""Dashboard view model: read one crawl bundle into plain dicts the template lays out. Captured data is untrusted."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from ..dimensions.security import HEADERS as SECURITY_HEADERS
from ..report.analyze import latest, verify

MISSING, UNREADABLE = "not collected", "unreadable"
# Site-level reports shown as-is; per-page reports are folded into the page cards and only linked raw.
SITE = ["robots", "sitemap", "crawler-access", "redirects", "llms", "feeds"]
PER_PAGE = ["indexing", "headers", "schema", "aeo", "measurement", "social-preview", "accessibility", "security", "fonts",
            "copy-scores"]
DIMENSIONS = ["security", "fonts", "meta_ads", "llm_reputation", "jev_copy"]
AREAS = ["Content", "SEO", "AEO", "Social", "Accessibility", "Analytics", "Security"]
SORTS = ("issues", "path", "type", "slop", "bias", "jev", *(a.lower() for a in AREAS))
COPY = {"slop": ("ai_slop", "AI slop"), "bias": ("marketing_bias", "Marketing bias")}
RANK = {"critical": 0, "serious": 1, "warning": 2, "neutral": 3, "good": 4}
TITLE_MAX, DESCRIPTION_MAX = 60, 160  # ponytail: common search-snippet lengths; tune if they flag too much.
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


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


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


def content_link(bundle, page):
    """A normalized path inside the bundle, or None: file_url raises on anything outside the root, and a tampered
    content_path (absolute, ../, NUL byte) must not 500 the page."""
    try:
        return (bundle / page["content_path"]).resolve().relative_to(bundle.resolve()).as_posix() \
            if isinstance(page.get("content_path"), str) else None
    except (ValueError, OSError):
        return None


def area(name, problems, summary, details=()):
    """One verdict row on a page card. problems: [(level, text)]; the worst one sets the level and the headline."""
    if problems:
        worst = min(problems, key=lambda p: RANK[p[0]])
        more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
        return {"name": name, "level": worst[0], "summary": worst[1] + more, "problems": len(problems),
                "details": [t for _, t in problems] + list(details)}
    return {"name": name, "level": "good", "summary": summary, "problems": 0, "details": list(details)}


def unchecked(name, summary="Not collected in this run"):
    return {"name": name, "level": "neutral", "summary": summary, "problems": 0, "details": []}


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def score(p, key):
    """A page's 0-100 copy score, or None (not collected, too short, or tampered)."""
    return num(as_dict(as_dict(p.get("copy_scores")).get(key)).get("score"))


def copy_lines(p):
    """Content-area summary suffix, problems and details for the AI slop and marketing bias scores."""
    scores = p.get("copy_scores")
    if not isinstance(scores, dict):
        return "", [], ["Copy scores: not collected in this run"]
    suffix, problems, details = [], [], []
    for key, label in COPY.values():
        c = as_dict(scores.get(key))
        value, level = num(c.get("score")), str(c.get("level") or "UNKNOWN")
        if value is None:
            details.append(f"{label}: too little copy to score")
            continue
        top = [str(t).replace("_", " ") for t in as_list(c.get("top_signals"))[:2]]
        suffix.append(f"{label} {value} {level}")
        if level == "HIGH":
            problems.append(("warning", f"{label} {value} (high)" + (f": {', '.join(top)}" if top else "")))
        details.append(f"{label} {value} ({level})" + (f" · top: {', '.join(top)}" if top else ""))
        for name, signal in as_dict(c.get("signals")).items():
            signal = as_dict(signal)
            if not num(signal.get("subscore")):
                continue
            example = next((e for e in as_list(signal.get("examples")) if isinstance(e, str)), "")
            label_, count = str(name).replace("_", " "), num(signal.get("count")) or 0
            what = (f"sentence-length variation {signal.get('cv')}" if name == "rhythm"
                    else "no balance markers" if name == "one_sidedness" and not count
                    else f"{count} {'hit' if count == 1 else 'hits'}")
            note = " (lowers the score)" if name == "specificity" else ""
            details.append(f"  {label_}: {signal['subscore']}/100, {what}{note}" + (f" · “{example}”" if example else ""))
    return (" · " + " · ".join(suffix)) if suffix else "", problems, details


def jev_lines(j):
    """Content-area suffix and details for the Jev judgment of one page (technical/jev_copy.json entry)."""
    if not j:
        return "", []
    if j.get("error"):
        return "", [f"AI slop (Jev): not judged, {j['error']}"]
    s = as_dict(j.get("ai_slop"))
    value, confidence = num(s.get("score")), num(s.get("confidence"))
    if value is None:
        return "", []
    probability = lambda v: f"{round(v * 100)}%" if num(v) is not None else "—"
    return (f" · Jev {value} {s.get('level')}",
            [f"AI slop (Jev): {value} ({s.get('level')}), confidence {probability(confidence)} · first-hand detail "
             f"{probability(j.get('first_hand'))} · generic {probability(j.get('generic'))}"])


def page_areas(p, by_url, collected):
    """Every per-page signal, grouped into the card's areas."""
    url, status, extracted = p.get("url"), p.get("status"), isinstance(p.get("visible_text"), str)
    problems = []
    if p.get("error"):
        problems.append(("critical", f"Failed to load: {p['error']}"))
    elif num(status) is not None and status >= 400:
        problems.append(("critical", f"HTTP {status}"))
    if not p.get("error") and p.get("extraction_status") not in (None, "EXTRACTED"):
        problems.append(("warning", f"Not extracted: {p.get('extraction_status')}"))
    if p.get("duplicate_of"):
        problems.append(("warning", f"Duplicate of {p['duplicate_of']}"))
    if p.get("truncated"):
        problems.append(("warning", "Response truncated at the byte limit"))
    words, ctas = len(p["visible_text"].split()) if extracted else 0, len(as_list(p.get("ctas")))
    suffix, copy_problems, copy_details = copy_lines(p) if extracted else ("", [], [])
    jev_suffix, jev_details = jev_lines(as_dict(by_url["jev_copy"].get(url)))
    suffix, copy_details = suffix + jev_suffix, copy_details + jev_details
    out = [area("Content", problems + copy_problems, f"HTTP {status} · {plural(words, 'word')} · {plural(ctas, 'CTA')}{suffix}",
                ([f"Emails: {', '.join(map(str, as_list(p.get('emails'))))}"] if as_list(p.get("emails")) else []) + copy_details)]
    if not extracted:
        return out + [unchecked(name, "Page text not extracted") for name in AREAS[1:]]

    title, description = text(p.get("title")), text(p.get("meta_description"))
    h1 = [text(h.get("text")) or "(empty)" for h in as_list(p.get("headings")) if isinstance(h, dict) and h.get("level") == 1]
    index = as_dict(by_url["indexing"].get(url))
    problems = []
    if not title:
        problems.append(("serious", "No <title>"))
    elif len(title) > TITLE_MAX:
        problems.append(("warning", f"Title is {len(title)} characters (aim for {TITLE_MAX} or fewer)"))
    if not description:
        problems.append(("warning", "No meta description"))
    elif len(description) > DESCRIPTION_MAX:
        problems.append(("warning", f"Meta description is {len(description)} characters (aim for {DESCRIPTION_MAX} or fewer)"))
    if not h1:
        problems.append(("warning", "No H1 heading"))
    elif len(h1) > 1:
        problems.append(("warning", f"{len(h1)} H1 headings"))
    robots = " ".join(str(v) for v in as_dict(p.get("robots_meta")).values()).lower()
    if index.get("noindex_observed") or "noindex" in robots:
        problems.append(("warning", "Marked noindex"))
    canonical = text(p.get("canonical_url"))
    if canonical and isinstance(url, str) and canonical.rstrip("/") != url.rstrip("/"):
        problems.append(("warning", f"Canonical points to {canonical}"))
    if index.get("extractability") in ("FAIL", "WARNING"):
        problems.append(("warning", "Little extractable text for search and AI"))
    out.append(area("SEO", problems, "Title, description, H1 and canonical look right",
                    [f"Title: {title}"] * bool(title) + [f"Description: {description}"] * bool(description)
                    + [f"H1: {h}" for h in h1[:3]]))

    ld = as_dict(p.get("json_ld"))
    types = [t for t in as_list(ld.get("types")) if isinstance(t, str)]
    problems = [("serious", "JSON-LD syntax error")] * len(as_list(ld.get("errors")))
    problems += [("serious" if i.get("severity") == "error" else "warning", str(i.get("message") or i.get("code")))
                 for i in as_list(ld.get("issues")) if isinstance(i, dict)]
    aeo = area("AEO", problems, f"JSON-LD: {', '.join(types)}", [f"Types: {', '.join(types)}"] if types else [])
    out.append(aeo if types or problems else unchecked("AEO", "No structured data (JSON-LD)"))

    if not collected["social-preview"]:
        out.append(unchecked("Social"))
    else:
        preview = as_dict(by_url["social-preview"].get(url))
        issues = [i for i in as_list(preview.get("issues")) if isinstance(i, dict)]
        out.append(area("Social", [("serious" if i.get("severity") == "error" else "warning",
                                    f"{i.get('tag')}: {str(i.get('code', '')).replace('_', ' ')}") for i in issues],
                        "Preview tags look right"))

    a11y = p.get("accessibility")
    if not isinstance(a11y, dict):
        out.append(unchecked("Accessibility"))
    else:
        findings = [f for f in as_list(a11y.get("findings")) if isinstance(f, dict)]
        out.append(area("Accessibility", [("warning", f"{f.get('rule_id')} (WCAG {as_dict(f.get('wcag')).get('criterion')}): "
                                                      f"{f.get('message')}") for f in findings],
                        "No barriers found by the automated checks"))

    if not collected["measurement"]:
        out.append(unchecked("Analytics"))
    else:
        tools = [str(m.get("tool")) for m in as_list(p.get("measurement")) if isinstance(m, dict)]
        out.append(area("Analytics", [] if tools else [("warning", "No analytics tag in the server HTML")],
                        ", ".join(dict.fromkeys(tools))))

    security = by_url["security"].get(url)
    if not isinstance(security, dict):
        out.append(unchecked("Security"))
    else:
        missing = [str(h) for h in as_list(security.get("missing_headers"))]
        problems = [("critical", "Not served over HTTPS")] * (security.get("https") is False)
        problems += [("serious", f"Mixed content: {plural(len(as_list(security.get('mixed_content'))), 'insecure resource')}")] \
            * bool(as_list(security.get("mixed_content")))
        problems += [("warning", f"{plural(len(missing), 'security header')} missing")] * bool(missing)
        out.append(area("Security", problems, "All checked headers present", [f"Missing: {h}" for h in missing]))
    return out


def page_cards(bundle, raw, sort="issues", desc=False):
    bundle = Path(bundle)
    by_url = {name: {e["url"]: e for e in as_list(entries) if isinstance(e, dict) and isinstance(e.get("url"), str)}
              for name, entries in (("indexing", raw["indexing"]), ("social-preview", as_dict(raw["social-preview"]).get("pages")),
                                    ("security", as_dict(raw["security"]).get("pages")),
                                    ("jev_copy", as_dict(raw["jev_copy"]).get("pages")))}
    collected = {name: isinstance(raw[name], dict) for name in ("social-preview", "measurement")}
    cards = []
    for path in sorted((bundle / "pages").glob("*.json")):
        p = read(bundle, f"pages/{path.name}")
        base = {"id": path.stem, "json": f"pages/{path.name}"}
        if not isinstance(p, dict):
            cards.append({**base, "url": None, "path": path.name, "title": None, "label": UNREADABLE, "status": None, "depth": None,
                          "level": "critical", "issues": 1, "content": None,
                          "areas": [area("Content", [("critical", "Page file is unreadable")], "")]})
            continue
        areas = page_areas(p, by_url, collected)
        try:
            page_path = urlsplit(p.get("url") or "").path or "/"
        except ValueError:
            page_path = str(p.get("url"))
        worst = min((a["level"] for a in areas), key=RANK.get)
        cards.append({**base, "id": str(p.get("id", path.stem)), "url": p.get("url"), "path": page_path,
                      "title": text(p.get("title")), "status": p.get("status"), "depth": p.get("depth"),
                      "label": as_dict(p.get("classification")).get("label"), "content": content_link(bundle, p),
                      "level": worst if RANK[worst] < RANK["neutral"] else "good",
                      "issues": sum(a["problems"] for a in areas), "areas": areas,
                      "slop": score(p, "ai_slop"), "bias": score(p, "marketing_bias"),
                      "jev": num(as_dict(as_dict(by_url["jev_copy"].get(p.get("url"))).get("ai_slop")).get("score"))})
    return sorted(cards, key=card_order(sort), reverse=desc)


def card_order(sort):
    names = [a.lower() for a in AREAS]
    if sort in names:
        i = names.index(sort)
        # Within one area, unchecked ("neutral") sorts after passing: it says nothing about the page.
        order = {**RANK, "good": 3, "neutral": 4}
        return lambda c: (order[c["areas"][i]["level"]] if len(c["areas"]) > i else 5,
                          -(c["areas"][i]["problems"] if len(c["areas"]) > i else 0), sort_key(c["path"]))
    if sort in (*COPY, "jev"):  # Highest score first; unscored pages last.
        return lambda c: (c.get(sort) is None, -(c.get(sort) or 0), sort_key(c["path"]))
    if sort == "path":
        return lambda c: sort_key(c["path"])
    if sort == "type":
        return lambda c: (sort_key(c["label"]), sort_key(c["path"]))
    return lambda c: (RANK[c["level"]], -c["issues"], sort_key(c["path"]))


def report(bundle):
    path = latest(bundle, "analysis.json")
    analysis = read(path.parent, path.name) if path else MISSING
    found = analysis.get("findings") if isinstance(analysis, dict) else None
    findings = [{"id": f.get("id"), "verdict": f.get("verdict") or f.get("severity"), "title": f.get("title")}
                for f in (found if isinstance(found, list) else []) if isinstance(f, dict)]
    return {"md": latest(bundle, "report.md"), "pdf": latest(bundle, "report.pdf"), "analysis": path, "findings": findings}


def site_read(data):
    """What the LLM read off the site: identity fields as (label, text) rows, plus quotes marked verified or not."""
    data = as_dict(data)
    found = as_dict(data.get("identity"))
    join = lambda v: ", ".join(x for x in v if isinstance(x, str)) if isinstance(v, list) else v if isinstance(v, str) else ""
    rows = [(label, join(found.get(key))) for key, label in (
        ("company_name", "Name"), ("other_names", "Other names"), ("category", "Category"), ("offerings", "Sells"),
        ("site_icp", "Sells to"), ("cities", "Cities"), ("service_area", "Serves"), ("phones", "Phones"))]
    quotes = [q for q in as_list(found.get("evidence")) if isinstance(q, dict) and isinstance(q.get("quote"), str)]
    return {"rows": [(label, text) for label, text in rows if text], "quotes": quotes, "pages": as_list(data.get("pages")),
            "error": data.get("error")}


def verdicts(scores, identity, icp):
    """The reputation tab's three headline answers: right business? ICP fit? recommended? Each {key, icon, level, word, detail}."""
    out = []
    agree, conflict = as_list(identity.get("agree")), as_list(identity.get("conflict"))
    word, level, detail = {
        "confirmed": ("Confirmed", "good", f"{', '.join(map(str, agree))} match{'es' if len(agree) == 1 else ''} this site"),
        "mismatch": ("Confused with a namesake", "critical",
                     f"The model described another business ({', '.join(map(str, conflict))} differs)"),
        "unconfirmed": ("Unconfirmed", "neutral", "The answer stated nothing checkable beyond what the prompt gave it"),
    }.get(identity.get("verdict"), ("Not checked", "neutral", "This run predates the identity check"))
    out.append({"key": "identity", "icon": "id", "label": "Right business?", "word": word, "level": level, "detail": detail})
    word, level = {"aligned": ("Aligned", "good"), "partial": ("Partly aligned", "warning"),
                   "misaligned": ("Misaligned", "critical")}.get(icp.get("verdict"), ("Not checked", "neutral"))
    detail = icp.get("reason") or (f"The site sells to {icp['site_icp']}" if icp.get("site_icp") else
                                   "Add an ICP to the site profile to check it against the website")
    out.append({"key": "icp", "icon": "target", "label": "ICP fit", "word": word, "level": level, "detail": detail,
                "user_icp": icp.get("user_icp"), "site_icp": icp.get("site_icp")})
    rate = num(scores.get("mention_rate"))
    word, level, detail = {
        "recommended": ("Recommended", "good", f"Named in {round(rate * 100) if rate is not None else '?'}% of buyer answers"),
        "not_recommended": ("Known, not recommended", "warning", "Recognized by name but never named in buyer answers"),
        "not_found": ("Not found", "critical", "Not recognized by name or named in any buyer answer; it needs more "
                                               "exposure (listings, reviews, press) before assistants recommend it"),
    }.get(scores.get("visibility"), ("Unknown", "neutral", "No visibility result in this run"))
    out.append({"key": "visibility", "icon": "eye", "label": "AI recommends it?", "word": word, "level": level, "detail": detail})
    return out


def reputation(data):
    if data in (MISSING, UNREADABLE) or not isinstance(data, dict):
        return {"state": data if data in (MISSING, UNREADABLE) else UNREADABLE}
    if data.get("status") == "UNKNOWN":
        return {"state": None, "unknown": data.get("error") or data.get("reason")}
    if not isinstance(data.get("scores"), dict):  # Runs from before ranking: one branded answer.
        competitors = (data.get("analysis") or {}).get("competitors") if isinstance(data.get("analysis"), dict) else None
        return {"state": None, "legacy": {"answer": data.get("raw_answer"), "competitors": table(competitors)}}
    answers = [a for a in as_list(data.get("answers")) if isinstance(a, dict)]
    for a in answers:
        named = a.get("companies") if isinstance(a.get("companies"), list) else []
        a["named"] = ", ".join(c["name"] for c in named if isinstance(c, dict) and isinstance(c.get("name"), str))
    questions = [{"prompt": p.get("text"), "source": p.get("source"), "answers": [a for a in answers if a.get("prompt") == p.get("text")]}
                 for p in as_list(data.get("prompts")) if isinstance(p, dict)]
    board = [r for r in as_list(data["scores"].get("leaderboard")) if isinstance(r, dict)]
    top = max([num(r.get("mentions")) or 0 for r in board] + [1])
    board = [{**r, "width": round((num(r.get("mentions")) or 0) / top * 100)} for r in board]  # Bar length vs the leader.
    scores = {**data["scores"], "leaderboard": board,
              "diverging": diverging(as_dict(data["scores"].get("sentiment")).get("score"))}
    branded = as_dict(data.get("branded"))
    # The crawl dimension keeps the profile at the top level; a standalone reputation run keeps it in reputation.json.
    profile = as_dict(data.get("profile") or branded.get("profile"))
    return {"state": None, "scores": scores, "branded": branded, "questions": questions,
            "audience": as_dict(data.get("audience")), "identity": as_dict(branded.get("identity")),
            "icp_check": as_dict(data.get("icp_check")), "site_read": site_read(data.get("site_read")),
            "verdicts": verdicts(scores, as_dict(branded.get("identity")), as_dict(data.get("icp_check"))),
            "profile": [(label, ", ".join(v for v in profile[key] if isinstance(v, str)))
                        for key, label in (("names", "Names"), ("cities", "Cities"), ("phones", "Phones"),
                                           ("categories", "Categories"), ("profiles", "Profiles"))
                        if isinstance(profile.get(key), list) and profile[key]]}


LEVEL = {"PASS": "good", "COMPLETE": "good", "OBSERVED": "good", "WARNING": "warning", "PARTIAL": "warning",
         "FAIL": "critical", "ERROR": "critical"}
SEVERITY = ["critical", "serious", "warning"]
SECURITY_CHECKS = len(SECURITY_HEADERS) + 1  # Plus frame protection (x-frame-options or CSP frame-ancestors).
FONT_FAMILIES_WARN = 4  # ponytail: heuristic; more named families than this reads as inconsistent.
# CSS keywords and generic fallbacks, not typefaces a designer chose; they don't count toward inconsistency.
GENERIC_FONTS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif",
                 "ui-monospace", "ui-rounded", "emoji", "math", "fangsong", "inherit", "initial", "unset", "revert",
                 "revert-layer", "-apple-system", "blinkmacsystemfont"}


def named_fonts(fonts):
    return [f["family"] for f in as_list(fonts.get("families"))
            if isinstance(f, dict) and isinstance(f.get("family"), str) and f["family"].lower() not in GENERIC_FONTS]


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def meter(part, whole):
    part, whole = num(part), num(whole)
    return {"pct": round(max(0, min(1, part / whole)) * 100)} if part is not None and whole else None


def signed(value):
    return f"{value:+d}" if isinstance(value, int) and not isinstance(value, bool) else "n/a"


def tile(title, href, value, sub="", level="neutral", status="", bar=None):
    return {"title": title, "href": href, "value": value, "sub": sub, "level": level, "status": status, "meter": bar}


def tiles(model, raw):
    m, h, out = model["manifest"], model["header"], []
    counts = as_dict(m.get("counts"))
    pages, limit, skipped = num(counts.get("pages")) or 0, num(h["max_pages"]), num(counts.get("skipped")) or 0
    out.append(tile("Pages crawled", "#pages", pages, f"of {limit} limit · {skipped} skipped" if limit else f"{skipped} skipped",
                    LEVEL.get(m.get("status"), "neutral"), str(m.get("status") or ""), meter(pages, limit)))
    r = model["report"]
    verdicts = [f["verdict"] for f in r["findings"]]
    fails, warns = verdicts.count("FAIL"), verdicts.count("WARNING")
    out.append(tile("Report", "#report", len(r["findings"]) if r["md"] else "—",
                    "findings in report.md" + (" · PDF ready" if r["pdf"] else "") if r["md"] else "Not generated yet",
                    "critical" if fails else "warning" if warns else "good" if r["md"] else "neutral",
                    f"{fails} FAIL" if fails else f"{warns} WARNING" if warns else "Report ready" if r["md"] else "No report"))
    t = raw["accessibility"]
    if isinstance(t, dict):
        out.append(tile("Accessibility (WCAG)", "?sort=accessibility#pages", num(t.get("finding_count")) or 0,
                        f"potential barriers · {t.get('pages_checked', 0)} pages checked",
                        LEVEL.get(t.get("automated_status"), "neutral"), str(t.get("automated_status") or "")))
    t = raw["copy-scores"]
    if isinstance(t, dict):
        for sort, (key, label) in COPY.items():
            c = as_dict(t.get(key))
            median, high, scored = num(c.get("median")), num(c.get("high")) or 0, num(c.get("pages")) or 0
            level = "neutral" if median is None else "serious" if median >= 60 else "warning" if median >= 30 or high else "good"
            out.append(tile(label, f"?sort={sort}#pages", median if median is not None else "—",
                            f"median of {plural(scored, 'page')} · 0-100, higher is more", level,
                            f"{high} HIGH" if high else "None HIGH" if scored else "Not scored", meter(median, 100)))
    t = raw["measurement"]
    if isinstance(t, dict):
        checked, missing = num(t.get("pages_checked")), num(t.get("pages_without_any_measurement_count")) or 0
        out.append(tile("Analytics", "?sort=analytics#pages", len(as_list(t.get("tools"))),
                        "tools · " + ("consent tool found" if t.get("has_consent_tool") else "no consent tool"),
                        "good" if t.get("has_measurement") else "serious", "Measured" if t.get("has_measurement") else "No analytics",
                        meter(checked - missing, checked) if checked else None))
    seo = [c for c in model["pages"] if any(a["name"] == "SEO" and RANK[a["level"]] < RANK["neutral"] for a in c["areas"])]
    checked = [c for c in model["pages"] if any(a["name"] == "SEO" and a["level"] != "neutral" for a in c["areas"])]
    if checked:
        out.append(tile("SEO basics", "?sort=seo#pages", len(checked) - len(seo), f"of {len(checked)} pages pass title, "
                        "description, H1 and canonical checks", "warning" if seo else "good",
                        plural(len(seo), "page") + " to fix" if seo else "All pass", meter(len(checked) - len(seo), len(checked))))
    t = raw["aeo"]
    if isinstance(t, dict):
        withld, checked = num(t.get("pages_with_json_ld")) or 0, num(t.get("pages_checked"))
        issues, broken = len(as_list(t.get("issue_summary"))), len(as_list(t.get("pages_with_syntax_errors")))
        out.append(tile("AEO structured data", "?sort=aeo#pages", f"{meter(withld, checked)['pct']}%" if checked else "—",
                        f"pages with JSON-LD · {plural(issues, 'issue type')}", "serious" if broken else "warning" if issues else "good",
                        plural(broken, "syntax error") if broken else plural(issues, "issue type") if issues else "No issues",
                        meter(withld, checked)))
    t = raw["social-preview"]
    if isinstance(t, dict):
        issues = len(as_list(t.get("issue_summary")))
        out.append(tile("Social previews", "?sort=social#pages", issues, f"issue {'type' if issues == 1 else 'types'} · {t.get('pages_checked', 0)} pages checked",
                        "warning" if issues else "good", "Needs work" if issues else "No issues"))
    t = raw["security"]
    if isinstance(t, dict):
        missing = as_list(t.get("missing_summary"))
        top = missing[0] if missing and isinstance(missing[0], dict) else {}
        out.append(tile("Security headers", "?sort=security#pages", f"{max(SECURITY_CHECKS - len(missing), 0)}/{SECURITY_CHECKS}",
                        f"headers present on every page · most missing: {top['header']}" if top.get("header")
                        else "headers present on every page",
                        "critical" if t.get("https") is False else "warning" if missing else "good",
                        {True: "HTTPS", False: "Not all HTTPS"}.get(t.get("https"), "HTTPS unknown"),
                        meter(SECURITY_CHECKS - len(missing), SECURITY_CHECKS)))
    t = raw["fonts"]
    if isinstance(t, dict):
        named = named_fonts(t)
        families = len(named)
        out.append(tile("Fonts", "#site", families,
                        f"named {'family' if families == 1 else 'families'} · most used: {named[0]}" if named else "named families",
                        "warning" if families > FONT_FAMILIES_WARN else "good",
                        "Many families" if families > FONT_FAMILIES_WARN else "Consistent"))
    t = raw["meta_ads"]
    if isinstance(t, dict):
        out.append(tile("Meta ads", "#meta_ads", num(t.get("ad_count")) if "ad_count" in t else "—",
                        "ads in the Ad Library" if "ad_count" in t else str(t.get("reason") or ""),
                        LEVEL.get(t.get("status"), "neutral"), str(t.get("status") or "")))
    rep = model["reputation"]
    if rep.get("scores") is not None:
        s = rep["scores"]
        rank, rate = num(s.get("rank")), num(s.get("mention_rate"))
        named = f" · named in {round(rate * 100)}% of buyer answers" if rate is not None else ""
        out.append(tile("AI reputation", "#reputation", f"#{rank}" if rank else "—",
                        (f"of {s.get('of')} companies" if rank else "unknown to the AI: needs more exposure"
                         if s.get("visibility") == "not_found" else "not named by the AI") + named,
                        "good" if rank == 1 else "warning" if rank else "serious",
                        f"Sentiment {signed(as_dict(s.get('sentiment')).get('score'))}", meter(rate, 1)))
    elif "legacy" in rep:
        out.append(tile("AI reputation", "#reputation", "—", "No ranking in this run"))
    elif "unknown" in rep:
        out.append(tile("AI reputation", "#reputation", "—", "The AI request failed", "neutral", "UNKNOWN"))
    return out


def attention(model, raw):
    """Anomalies worth a look, most severe first. Each is {level, text, href}."""
    items, m = [], model["manifest"]
    add = lambda level, text, href: items.append({"level": level, "text": text, "href": href})
    if isinstance(model["integrity"], list) and model["integrity"]:
        add("critical", f"{plural(len(model['integrity']), 'bundle file')} failed the integrity check", "#report")
    errors = len(as_list(m.get("errors")))
    if errors:
        add("serious", f"{plural(errors, 'page')} failed to load", "?sort=content#pages")
    verdicts = [f["verdict"] for f in model["report"]["findings"]]
    if verdicts.count("FAIL"):
        add("critical", f"{plural(verdicts.count('FAIL'), 'FAIL finding')} in the report", "#report")
    if verdicts.count("WARNING"):
        add("warning", f"{plural(verdicts.count('WARNING'), 'WARNING finding')} in the report", "#report")
    t = raw["copy-scores"]
    if isinstance(t, dict):
        for sort, (key, label) in COPY.items():
            high = num(as_dict(t.get(key)).get("high"))
            if high:
                add("warning", f"{plural(high, 'page')} {'scores' if high == 1 else 'score'} HIGH for {label}", f"?sort={sort}#pages")
    t = raw["security"]
    if isinstance(t, dict):
        if t.get("https") is False:
            add("critical", "Not every page is served over HTTPS", "?sort=security#pages")
        missing = [x for x in as_list(t.get("missing_summary")) if isinstance(x, dict)]
        if missing:
            add("warning", f"{plural(len(missing), 'security header')} missing (most: {missing[0].get('header')}, "
                           f"{missing[0].get('pages')} pages)", "?sort=security#pages")
    t = raw["accessibility"]
    if isinstance(t, dict) and num(t.get("finding_count")):
        add("warning", f"{plural(t['finding_count'], 'potential accessibility barrier')} (WCAG 2.2)", "?sort=accessibility#pages")
    t = raw["measurement"]
    if isinstance(t, dict):
        if not t.get("has_measurement"):
            add("serious", "No analytics detected in the server HTML", "?sort=analytics#pages")
        elif num(t.get("pages_without_any_measurement_count")):
            add("warning", f"{plural(t['pages_without_any_measurement_count'], 'page')} without an analytics tag", "?sort=analytics#pages")
        if t.get("has_measurement") and not t.get("has_consent_tool"):
            add("warning", "Analytics runs without a detected consent tool", "#site")
    seo = [c for c in model["pages"] if any(a["name"] == "SEO" and RANK[a["level"]] < RANK["neutral"] for a in c["areas"])]
    if seo:
        add("warning", f"{plural(len(seo), 'page')} with SEO issues (title, description, H1 or canonical)", "?sort=seo#pages")
    t = raw["aeo"]
    if isinstance(t, dict):
        broken = len(as_list(t.get("pages_with_syntax_errors")))
        if broken:
            add("serious", f"JSON-LD syntax errors on {plural(broken, 'page')}", "?sort=aeo#pages")
        if as_list(t.get("issue_summary")):
            add("warning", f"{plural(len(t['issue_summary']), 'structured-data issue type')}", "?sort=aeo#pages")
    t = raw["social-preview"]
    if isinstance(t, dict) and as_list(t.get("issue_summary")):
        add("warning", f"{plural(len(t['issue_summary']), 'social preview issue type')}", "?sort=social#pages")
    t = raw["fonts"]
    if isinstance(t, dict) and len(named_fonts(t)) > FONT_FAMILIES_WARN:
        add("warning", f"{len(named_fonts(t))} named font families declared", "#site")
    s = model["reputation"].get("scores")
    if s is not None:
        score = as_dict(s.get("sentiment")).get("score")
        if s.get("visibility") == "not_found":
            add("serious", "AI doesn't know this business: not recognized by name or named in any buyer answer", "#reputation")
        elif not num(s.get("rank")):
            add("serious", "Not named in any AI buyer answer", "#reputation")
        if num(score) is not None and score < 0:
            add("serious", f"Negative AI sentiment ({signed(score)})", "#reputation")
        if model["reputation"]["icp_check"].get("verdict") == "misaligned":
            add("warning", "Your ICP doesn't match who the website sells to", "#reputation")
        conflict = model["reputation"]["identity"].get("conflict")
        if model["reputation"]["identity"].get("verdict") == "mismatch" and isinstance(conflict, list):
            add("serious", f"AI describes a different business under this name ({', '.join(map(str, conflict))} differs)", "#reputation")
    return sorted(items, key=lambda i: SEVERITY.index(i["level"]))


def diverging(score):
    """Geometry for a -100..+100 bar that grows from a neutral midpoint."""
    score = num(score)
    if score is None:
        return None
    score = max(-100, min(100, score))
    return {"left": 50 if score >= 0 else 50 + score / 2, "width": abs(score) / 2, "sign": "pos" if score >= 0 else "neg"}


def info(title, level, status, facts=(), text_label=None, text=None, table_label=None, rows=None, note=None, file=None):
    """A site-level card: verdict chip, key facts, and optional raw text or table behind a toggle."""
    return {"title": title, "level": level, "status": status, "facts": [f for f in facts if f[1] not in (None, "")],
            "text_label": text_label, "text": text if isinstance(text, str) and text.strip() else None,
            "table_label": table_label, "table": table(rows) if rows else None, "note": note, "file": file}


def missing_card(title, value, file):
    return info(title, "neutral", "Unreadable" if value == UNREADABLE else "Not collected", file=None if value == MISSING else file)


def site_cards(bundle, raw):
    cards = []
    robots = raw["robots"]
    if isinstance(robots, dict):
        status, policy = robots.get("status"), robots.get("policy_status")
        declared = [line.split(":", 1)[1].strip() for line in str(robots.get("text") or "").splitlines()
                    if line.lower().startswith("sitemap:")]
        level, verdict = ("good", "Crawling rules found") if status == 200 and policy == "OBSERVED" else \
            ("good", "None: crawling allowed") if status in (404, 410) else ("serious", "Unknown: page crawl stopped")
        cards.append(info("robots.txt", level, verdict, [("HTTP status", status or robots.get("error")), ("Policy", policy),
                                                        ("Sitemaps declared", len(declared))],
                          "robots.txt", robots.get("text"), file="technical/robots.json"))
    else:
        cards.append(missing_card("robots.txt", robots, "technical/robots.json"))

    sitemap, discovery = raw["sitemap"], read(bundle, "discovery.json")
    if isinstance(sitemap, dict):
        docs = [d for d in as_list(sitemap.get("documents")) if isinstance(d, dict)]
        urls = len(as_list(as_dict(discovery).get("sitemap_urls")))
        ok = any(d.get("status") == 200 for d in docs)
        cards.append(info("Sitemap", "good" if ok else "warning", f"{plural(urls, 'URL')} listed" if ok else "No sitemap found",
                          [("Documents", len(docs)), ("URLs listed", urls), ("Limit reached", "yes" if sitemap.get("limit_reached") else "no")],
                          table_label="Sitemap documents",
                          rows=[{"url": d.get("url"), "status": d.get("status"), "type": d.get("type")} for d in docs],
                          file="technical/sitemap.json"))
    else:
        cards.append(missing_card("Sitemap", sitemap, "technical/sitemap.json"))

    access = raw["crawler-access"]
    if isinstance(access, dict):
        bots = []
        for check in as_list(access.get("checks")):
            if isinstance(check, dict):
                urls = [u for u in as_list(check.get("urls")) if isinstance(u, dict)]
                allowed = sum(u.get("robots_allowed") is True for u in urls)
                bots.append({"bot": check.get("agent"), "allowed": f"{allowed} of {len(urls)}", "blocked": len(urls) - allowed})
        blocked = [b for b in bots if b["blocked"]]
        cards.append(info("AI crawler access", "warning" if blocked else "good",
                          f"{plural(len(blocked), 'AI bot')} blocked on some pages" if blocked else f"All {len(bots)} AI bots allowed",
                          [("Bots checked", len(bots)), ("Blocked somewhere", ", ".join(str(b["bot"]) for b in blocked) or "none")],
                          table_label="Per bot", rows=bots, note=access.get("limitation"), file="technical/crawler-access.json"))
    else:
        cards.append(missing_card("AI crawler access", access, "technical/crawler-access.json"))

    llms = raw["llms"]
    if isinstance(llms, dict):
        present = llms.get("status") == 200
        cards.append(info("llms.txt", "good" if present else "neutral", "Present" if present else "Not present (optional)",
                          [("HTTP status", llms.get("status") or llms.get("error"))], "llms.txt", llms.get("text") if present else None,
                          note=llms.get("note"), file="technical/llms.json"))
    else:
        cards.append(missing_card("llms.txt", llms, "technical/llms.json"))

    redirects = raw["redirects"]
    if isinstance(redirects, list):
        rows = [{"from": r.get("url"), "to": r.get("final_url"), "hops": len(as_list(r.get("chain"))), "error": r.get("error")}
                for r in redirects if isinstance(r, dict)]
        long = [r for r in rows if r["hops"] > 1 or r["error"]]
        cards.append(info("Redirects", "warning" if long else "good" if rows else "neutral",
                          f"{plural(len(long), 'chain')} with several hops or errors" if long else plural(len(rows), "redirect"),
                          [("Redirects", len(rows)), ("Multi-hop or failed", len(long))], table_label="Redirects", rows=rows,
                          file="technical/redirects.json"))
    else:
        cards.append(missing_card("Redirects", redirects, "technical/redirects.json"))

    feeds = raw["feeds"]
    if isinstance(feeds, list):
        rows = [{"feed": f.get("url") or f.get("href"), "type": f.get("type"), "found on": f.get("source")} for f in feeds if isinstance(f, dict)]
        cards.append(info("Feeds (RSS/Atom)", "good" if rows else "neutral", plural(len(rows), "feed") if rows else "None found",
                          [("Feeds", len(rows))], table_label="Feeds", rows=rows, file="technical/feeds.json"))

    fonts = raw["fonts"]
    if isinstance(fonts, dict):
        named = named_fonts(fonts)
        cards.append(info("Fonts", "warning" if len(named) > FONT_FAMILIES_WARN else "good",
                          "Many families" if len(named) > FONT_FAMILIES_WARN else "Consistent",
                          [("Named families", ", ".join(named) or "none"), ("Most used", named[0] if named else None)],
                          table_label="Families across the site", rows=as_list(fonts.get("families")), note=fonts.get("limitation"),
                          file="technical/fonts.json"))
    return cards


def meta_ads_card(data):
    if not isinstance(data, dict):
        return missing_card("Meta Ad Library", data, "technical/meta_ads.json")
    observed = data.get("status") == "OBSERVED"
    ads = [a for a in as_list(data.get("ads")) if isinstance(a, dict)]
    return info("Meta Ad Library", LEVEL.get(data.get("status"), "neutral"),
                plural(num(data.get("ad_count")) or 0, "ad") + " found" if observed else f"Unknown: {data.get('reason') or 'not checked'}",
                [("Search terms", data.get("search_terms")), ("Countries", ", ".join(map(str, as_list(data.get("countries"))))),
                 ("More available", "yes" if data.get("more_available") else None), ("Error", data.get("error"))],
                table_label="Ads" if ads else "Advertisers",
                rows=[{"page": a.get("page_name"), "started": a.get("ad_delivery_start_time"), "stopped": a.get("ad_delivery_stop_time"),
                       "platforms": ", ".join(map(str, as_list(a.get("publisher_platforms")))), "snapshot": a.get("ad_snapshot_url")}
                      for a in ads] or [{"page": k, "ads": v} for k, v in as_dict(data.get("pages")).items()],
                note=data.get("note") or data.get("limitation"), file="technical/meta_ads.json")


def profile_cards(data):
    cards = []
    for p in as_list(as_dict(data).get("profiles")):
        if not isinstance(p, dict):
            continue
        confidence = num(p.get("official_confidence"))
        cards.append({"network": str(p.get("network") or "profile"), "url": p.get("url"),
                      "verified": p.get("verification_status") == "verified",
                      "status": str(p.get("status") or "").replace("_", " ").lower(),
                      "confidence": f"{round(confidence * 100)}%" if confidence is not None else None,
                      "evidence": len(as_list(p.get("evidence")))})
    return cards


def standalone_reputation(bundle, host):
    """The latest reputation-only run for this site (`companyscan reputation`, or one started from the UI) that sits next
    to the crawl bundle, reshaped like technical/llm_reputation.json. Returns (data, source) or (MISSING, None)."""
    runs = []
    for manifest in Path(bundle).parent.glob("*/manifest.json"):
        m = read(manifest.parent, "manifest.json")
        if isinstance(m, dict) and m.get("command") == "reputation" and isinstance(m.get("input_url"), str) \
                and m["input_url"].removeprefix("www.") == str(host).removeprefix("www."):
            runs.append((str(m.get("created_at") or ""), manifest.parent, m))
    if not runs:
        return MISSING, None
    created, run, m = max(runs, key=lambda r: r[0])
    answers, scores = read(run, "reputation/answers.json"), read(run, "reputation/scores.json")
    if not (isinstance(answers, dict) and isinstance(scores, dict)):
        return UNREADABLE, None
    data = {"status": m.get("status"), "branded": read(run, "reputation/reputation.json"), "audience": answers.get("audience"),
            "prompts": answers.get("prompts"),
            "answers": answers.get("answers"), "scores": scores}
    return data, {"dir": run.name, "created_at": created, "model": m.get("model")}


def company_names(data):
    """Each distinct name once, with how many pages state it (the same Organization JSON-LD repeats on every page)."""
    names = {}
    for n in as_list(as_dict(data).get("names")):
        if isinstance(n, dict) and isinstance(n.get("value"), str):
            entry = names.setdefault(n["value"], {"value": n["value"], "kind": n.get("kind"), "source": n.get("source"), "pages": 0})
            entry["pages"] += 1
    return sorted(names.values(), key=lambda n: -n["pages"])


def coverage(bundle, manifest, urls):
    skipped = [x for x in as_list(as_dict(urls).get("skipped")) if isinstance(x, dict)]
    reasons = {}
    for x in skipped:
        reasons[str(x.get("reason"))] = reasons.get(str(x.get("reason")), 0) + 1
    files = [a.get("path") for a in as_list(manifest.get("artifacts")) if isinstance(a, dict) and isinstance(a.get("path"), str)]
    return {"reasons": sorted(reasons.items(), key=lambda r: -r[1]), "skipped": table(skipped), "errors": table(manifest.get("errors")),
            "limitations": [str(x) for x in as_list(manifest.get("limitations"))],
            "raw": [f for f in files if f.startswith(("technical/", "social/")) or "/" not in f]}


def load(bundle, sort="issues", desc=False):
    bundle = Path(bundle)
    manifest = read(bundle, "manifest.json")
    manifest = manifest if isinstance(manifest, dict) else {}
    try:
        integrity = verify(bundle)
    except (OSError, ValueError, KeyError, TypeError):
        integrity = UNREADABLE
    raw = {name: read(bundle, f"technical/{name}.json") for name in dict.fromkeys(SITE + PER_PAGE + DIMENSIONS)}
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    urls = read(bundle, "urls.json")
    try:
        host = urlsplit(str(manifest.get("input_url", ""))).netloc or manifest.get("input_url")
    except ValueError:
        host = str(manifest.get("input_url"))
    # The crawl's own llm_reputation wins; without it, show the latest reputation-only run for the same site.
    rep_raw, rep_source = raw["llm_reputation"], None
    if rep_raw == MISSING:
        rep_raw, rep_source = standalone_reputation(bundle, host)
    model = {
        "manifest": manifest, "integrity": integrity,
        "header": {"host": host,
                   "created_at": manifest.get("created_at", ""), "status": manifest.get("status"), "command": manifest.get("command"),
                   "counts": as_dict(manifest.get("counts")), "max_pages": config.get("max_pages"), "max_depth": config.get("max_depth"),
                   "dimensions": as_list(config.get("dimensions")), "errors": len(as_list(manifest.get("errors")))},
        "report": report(bundle),
        "pages": page_cards(bundle, raw, sort if sort in SORTS else "issues", desc), "sort": sort if sort in SORTS else "issues",
        "desc": desc, "areas": AREAS,
        "sorts": [("issues", "Most issues"), ("path", "URL"), ("type", "Type")] + [(a.lower(), a) for a in AREAS]
                 + [(k, label) for k, (_, label) in COPY.items()] + [("jev", "AI slop (Jev)")],
        "site": site_cards(bundle, raw),
        "meta_ads": meta_ads_card(raw["meta_ads"]),
        "reputation": reputation(rep_raw),
        "profiles": profile_cards(read(bundle, "social/discovered.json")),
        "names": company_names(read(bundle, "company.json")),
        "coverage": coverage(bundle, manifest, urls),
    }
    model["reputation"]["source"] = rep_source
    model["tiles"] = tiles(model, raw)
    model["attention"] = attention(model, raw)
    return model
