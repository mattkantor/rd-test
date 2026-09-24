"""Per-page AI slop and marketing bias scores from captured copy. Deterministic heuristics: evidence to review, never
proof of AI authorship or wrongdoing. Matches are OBSERVED; scores are INFERRED."""
import re
import statistics
from collections import Counter

LEXICON_VERSION = "2026-09-23"
MIN_WORDS = 80
CHROME_SHARE, CHROME_MIN_PAGES = 0.5, 3  # Lines on half the pages or more are nav/footer, not page copy.
SKELETON_SHARE = 0.2  # ponytail: a line opening reused on a fifth of pages (below chrome) reads as a template skeleton.
LEVELS = ((60, "HIGH"), (30, "MEDIUM"), (0, "LOW"))


def phrases(*words):
    """Case-insensitive, whole-word alternation of literal phrases (lookarounds, so "#1" and "100%" match too)."""
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in words) + r")(?!\w)", re.I)


STOCK = phrases(
    "delve", "delves", "delving", "leverage", "leverages", "leveraging", "seamless", "seamlessly", "robust", "elevate",
    "elevates", "unlock", "unlocks", "unlocking", "empower", "empowers", "empowering", "streamline", "streamlines",
    "streamlined", "landscape", "game-changer", "game-changing", "cutting-edge", "tapestry", "testament", "pivotal",
    "realm", "embark", "navigate the complexities", "ever-evolving", "fast-paced", "synergy", "synergies", "holistic",
    "transformative", "harness", "harnessing", "supercharge", "revolutionize", "next-level", "unparalleled",
    "meticulous", "meticulously", "bespoke", "curated", "foster", "fostering", "paramount", "vibrant", "dynamic",
    "comprehensive", "innovative", "state-of-the-art", "a myriad of", "plethora", "in the world of", "journey",
    "resonate", "resonates", "crucial", "moreover", "furthermore", "additionally")
CONTRAST = re.compile(r"\b(?:not\s+(?:just|only|merely)\b[^.!?]{0,80}?\bbut\b|isn['’]t\s+just\b|(?:it|this|that)['’]s\s+not\s+"
                      r"(?:about\s+)?[^.!?,]{1,40},\s+(?:it|this|that)['’]s\b)", re.I)
OPENERS = phrases(
    "in today's", "in today’s", "whether you're", "whether you’re", "look no further", "here's the thing",
    "here’s the thing", "the short answer", "the honest answer", "the truth is", "let's dive in", "let’s dive in",
    "let's dive", "it's important to note", "it’s important to note", "it's worth noting", "at the end of the day",
    "in conclusion", "when it comes to", "imagine a world", "are you tired of")
TRIAD = re.compile(r"\b[a-z]+(?:ly)?,\s+[a-z]+,?\s+and\s+[a-z]+\b", re.I)
TEMPLATE = re.compile(r"lorem ipsum|\{\{|\[your [^\]]{1,30}\]|\bin your area\b|this headline grabs|your (?:headline|title) here|"
                      r"insert [a-z ]{1,20} here", re.I)
# Numbers with a unit or noun after them; years and dates are not specifics.
NUMBER = re.compile(r"(?<![\w.])(?!(?:19|20)\d\d\b)(?:\$|£|€)?\d[\d,.]*\s?(?:%|x\b|k\b|m\b|(?!(?:am|pm|th|st|nd|rd)\b)[a-z]{3,})", re.I)

PUFFERY = phrases(
    "best", "leading", "world-class", "world class", "#1", "number one", "revolutionary", "unmatched", "unrivaled",
    "industry-leading", "premier", "top-rated", "top rated", "best-in-class", "second to none", "unbeatable",
    "always", "never fails", "guaranteed", "guarantee", "100%", "the only company", "the only agency", "the only firm",
    "the only platform", "the only solution", "the only team")
STAT = re.compile(r"\d[\d,.]*\s?(?:%|x\b|\+)|\b\d[\d,]*\s+(?:clients|customers|companies|meetings|leads|users|businesses)\b", re.I)
# Before/after measurements ("from 0.97% to 2.73%", "$285 → $118") are specifics, not boasts.
MEASURED = re.compile(r"\bfrom\b[^!?\n]{0,40}?\bto\b|→|->", re.I)  # Decimals allowed: "from 0.97% to".
SOURCED = re.compile(r"\b(?:source|according to|study|survey|report(?:ed)? by|data from|research|per\s+[A-Z])", re.I)
WE, YOU = re.compile(r"\b(?:we|we['’](?:re|ve|ll)|our|ours|us)\b", re.I), re.compile(r"\b(?:you|your|yours|you['’](?:re|ve|ll))\b", re.I)
BALANCE = phrases(
    "not a fit", "not a good fit", "isn't for", "isn’t for", "not for everyone", "not right for", "limitation",
    "limitations", "trade-off", "trade-offs", "tradeoff", "downside", "downsides", "drawback", "drawbacks",
    "we don't", "we don’t", "we won't", "we won’t", "if you're not", "if you’re not", "won't work", "won’t work")
PRESSURE = re.compile(r"\b(?:limited[- ]time|act (?:now|fast)|hurry|ends soon|last chance|today only|while (?:supplies|spots) last|"
                      r"only \d+ (?:spots?|seats?|places?|left|remaining|openings?)|spots? (?:are )?(?:filling|limited)|"
                      r"(?:offer|deal|discount|pricing) (?:ends|expires)|deadline is (?:approaching|near|coming)|book (?:now|today) before)\b", re.I)
FOMO = re.compile(r"\b(?:don['’]t miss|don['’]t get left behind|left behind|your competitors (?:are|already)|before it['’]s too late|"
                  r"everyone (?:else )?is (?:already|using|switching)|join (?:over )?\d[\d,]*\+?|thousands of (?:companies|teams|businesses)|"
                  r"missing out|fear of missing)\b", re.I)
LOSS = re.compile(r"\b(?:stop losing|you['’]re losing|losing (?:money|deals|leads|clients|customers)|cost of (?:inaction|waiting|doing nothing)|"
                  r"leaving money on the table|falling behind|fall behind|wasting|wasted|missed opportunit(?:y|ies)|"
                  r"costs? you|bleeding)\b", re.I)
AUTHORITY = re.compile(r"\b(?:experts?|certified|award[- ]winning|as seen (?:in|on)|trusted by|featured in|recognized by|accredited|"
                       r"\d+\+?\s+years of experience|industry veterans?|official partner|partnered with)\b", re.I)

# (signal, weight, per-1k-words rate that scores 100). ponytail: thresholds calibrated on two corpora; retune with more.
SLOP = [("stock_phrases", 25, 12), ("rhythm", 15, None), ("formula_skeleton", 15, None), ("contrast_frames", 15, 3),
        ("formula_openers", 10, 3), ("em_dashes", 10, 12), ("triads", 10, 6)]
BIAS = [("unsupported_claims", 20, 10), ("self_focus", 15, None), ("one_sidedness", 15, None), ("pressure", 15, 3),
        ("fomo", 10, 3), ("loss_aversion", 10, 4), ("authority", 15, 5)]


def level(score):
    return "UNKNOWN" if score is None else next(name for floor, name in LEVELS if score >= floor)


def snippets(text, matches, limit=5):
    out = []
    for m in matches[:limit]:
        start, end = max(0, m.start() - 40), min(len(text), m.end() + 40)
        out.append(("…" if start else "") + re.sub(r"\s+", " ", text[start:end]).strip() + ("…" if end < len(text) else ""))
    return out


def rated(name, text, matches, words, cap):
    per_1k = len(matches) / words * 1000
    return {"count": len(matches), "per_1k": round(per_1k, 1), "subscore": round(min(per_1k / cap, 1) * 100),
            "examples": snippets(text, matches)}


def sentences(text):
    # Lines under 6 words are headings, buttons and labels, not prose.
    prose = [line for line in text.splitlines() if len(line.split()) >= 6]
    return [s for line in prose for s in re.split(r"(?<=[.!?])\s+", line) if len(s.split()) >= 3]


def rhythm(text):
    lengths = [len(s.split()) for s in sentences(text)]
    if len(lengths) < 8:
        return {"count": len(lengths), "cv": None, "subscore": 0, "examples": [], "note": "Too few sentences to judge"}
    cv = statistics.pstdev(lengths) / statistics.mean(lengths)
    # ponytail: CV <= 0.25 reads machine-uniform, >= 0.6 reads human-varied.
    return {"count": len(lengths), "cv": round(cv, 2), "mean_words": round(statistics.mean(lengths), 1),
            "subscore": round(max(0, min(1, (0.6 - cv) / 0.35)) * 100), "examples": []}


def opening(line):
    return " ".join(re.findall(r"[a-z']+", line.lower())[:3])


def skeleton(text, common):
    """Lines (headings included) that open the way many other pages do: identical post templates."""
    hits = [line for line in text.splitlines() if len(line.split()) >= 2 and opening(line) in common]
    return {"count": len(hits), "subscore": round(min(len(hits) / 4, 1) * 100), "examples": [h[:120] for h in hits[:5]]}


def ai_slop(text, words, common=frozenset(), raw=None):
    signals = {
        "stock_phrases": rated("stock_phrases", text, list(STOCK.finditer(text)), words, 12),
        "rhythm": rhythm(text),
        "formula_skeleton": skeleton(text, common),
        "contrast_frames": rated("contrast_frames", text, list(CONTRAST.finditer(text)), words, 3),
        "formula_openers": rated("formula_openers", text, list(OPENERS.finditer(text)), words, 3),
        "em_dashes": rated("em_dashes", text, list(re.finditer("—", text)), words, 12),
        "triads": rated("triads", text, list(TRIAD.finditer(text)), words, 6),
    }
    score = sum(signals[name]["subscore"] * weight / 100 for name, weight, _ in SLOP)
    raw = raw or text  # Placeholders repeated on every page look like chrome, so check the full page text.
    template = list(TEMPLATE.finditer(raw))
    signals["template_artifacts"] = {"count": len(template), "subscore": 100 if template else 0, "examples": snippets(raw, template)}
    numbers = list(NUMBER.finditer(text))
    specific = rated("specificity", text, numbers, words, 25)
    signals["specificity"] = {**specific, "note": "Counter-signal: numbers with context lower the score"}
    score = score + 40 * bool(template) - 10 * specific["subscore"] / 100
    return finish(score, signals, [n for n, *_ in SLOP] + ["template_artifacts"])


def self_focus(text, brand):
    we = list(WE.finditer(text))
    if brand:
        we += list(re.finditer(r"\b" + re.escape(brand) + r"\b", text, re.I))
    you = list(YOU.finditer(text))
    first = next((s for s in sentences(text)), "")
    opens_on_self = bool(re.match(r"(?:we|our)\b", first, re.I) or (brand and first.lower().startswith(brand.lower())))
    share = len(we) / (len(we) + len(you)) if we or you else 0.5
    # ponytail: a 40/60 we:you split is balanced; 80% or more company-talk scores 100. Under 5 pronouns is too few to say.
    subscore = round(max(0, min(1, (share - 0.4) / 0.4)) * min(1, (len(we) + len(you)) / 5) * 100)
    return {"count": len(we), "we": len(we), "you": len(you), "we_share": round(share, 2), "opens_on_self": opens_on_self,
            "subscore": min(100, subscore + 20 * opens_on_self), "examples": snippets(text, we)}


def unsupported(text, words, brand=None):
    names = [m.span() for m in re.finditer(re.escape(brand), text, re.I)] if brand else []
    matches = [m for m in PUFFERY.finditer(text) if not any(a <= m.start() < b for a, b in names)]  # "Best Leads" isn't a boast.
    for m in STAT.finditer(text):  # A statistic counts only when its own sentence names no source.
        start = max(text.rfind(c, 0, m.start()) for c in "!?\n") + 1
        start = max(start, text.rfind(". ", 0, m.start()) + 1)
        ends = [i for i in (text.find(c, m.end()) for c in ("!", "?", "\n", ". ")) if i >= 0]
        sentence = text[start:min(ends, default=len(text))]
        if not (SOURCED.search(sentence) or MEASURED.search(sentence)):
            matches.append(m)
    matches.sort(key=lambda m: m.start())
    return rated("unsupported_claims", text, matches, words, 10)


def one_sided(text, words):
    matches = list(BALANCE.finditer(text))
    if words < 300:
        return {"count": len(matches), "subscore": 0, "examples": snippets(text, matches), "note": "Too short to expect balance"}
    return {"count": len(matches), "subscore": max(0, 100 - 50 * len(matches)), "examples": snippets(text, matches),
            "note": "Examples are balance markers; none found means all upside"}


def marketing_bias(text, words, brand):
    signals = {
        "unsupported_claims": unsupported(text, words, brand),
        "self_focus": self_focus(text, brand),
        "one_sidedness": one_sided(text, words),
        "pressure": rated("pressure", text, list(PRESSURE.finditer(text)), words, 3),
        "fomo": rated("fomo", text, list(FOMO.finditer(text)), words, 3),
        "loss_aversion": rated("loss_aversion", text, list(LOSS.finditer(text)), words, 4),
        "authority": rated("authority", text, list(AUTHORITY.finditer(text)), words, 5),
    }
    score = sum(signals[name]["subscore"] * weight / 100 for name, weight, _ in BIAS)
    return finish(score, signals, [n for n, *_ in BIAS])


def finish(score, signals, order):
    score = round(max(0, min(100, score)))
    top = sorted((n for n in order if signals[n]["subscore"]), key=lambda n: -signals[n]["subscore"])
    return {"score": score, "level": level(score), "top_signals": top[:3], "signals": signals, "kind": "INFERRED"}


def chrome(pages):
    """Lines shared by most pages (navigation, footer, cookie banners)."""
    texts = [p["visible_text"] for p in pages]
    if len(texts) < CHROME_MIN_PAGES:
        return set()
    counts = Counter(line for t in texts for line in set(t.splitlines()) if line.strip())
    return {line for line, n in counts.items() if n / len(texts) >= CHROME_SHARE}


def score_text(text, brand=None, common=frozenset(), raw=None):
    words = len(re.findall(r"[A-Za-z][A-Za-z'’-]*", text))
    if words < MIN_WORDS:
        empty = {"score": None, "level": "UNKNOWN", "top_signals": [], "signals": {}, "kind": "INFERRED",
                 "note": f"Fewer than {MIN_WORDS} words of page copy"}
        return {"words_scored": words, "ai_slop": empty, "marketing_bias": dict(empty)}
    return {"words_scored": words, "ai_slop": ai_slop(text, words, common, raw), "marketing_bias": marketing_bias(text, words, brand)}


def score_pages(pages, brand=None):
    """Add page["copy_scores"] to every extracted page and return the site summary (technical/copy-scores.json)."""
    usable = [p for p in pages if isinstance(p.get("visible_text"), str) and not p.get("duplicate_of")]
    shared = chrome(usable)
    bodies = {id(p): "\n".join(line for line in p["visible_text"].splitlines() if line not in shared) for p in usable}
    common = skeleton_openings(bodies.values())
    for p in usable:
        body = bodies[id(p)]
        p["copy_scores"] = {"lexicon_version": LEXICON_VERSION,
                            "chrome_lines_removed": len(p["visible_text"].splitlines()) - len(body.splitlines()),
                            **score_text(body, brand, common, p["visible_text"])}
    return summary(usable, shared, common)


def skeleton_openings(bodies):
    """Three-word prose-line openings used on SKELETON_SHARE+ of pages (min CHROME_MIN_PAGES pages)."""
    bodies = list(bodies)
    counts = Counter(o for b in bodies for o in {opening(line) for line in b.splitlines() if len(line.split()) >= 2})
    floor = max(CHROME_MIN_PAGES, SKELETON_SHARE * len(bodies))
    return frozenset(o for o, n in counts.items() if n >= floor and o)


def stats(values):
    values = [v for v in values if v is not None]
    return {"pages": len(values), "median": round(statistics.median(values)) if values else None,
            "mean": round(statistics.mean(values)) if values else None,
            "high": sum(v >= 60 for v in values), "medium": sum(30 <= v < 60 for v in values)}


def summary(pages, shared, common=frozenset()):
    out = {"lexicon_version": LEXICON_VERSION, "pages_scored": sum(p["copy_scores"]["ai_slop"]["score"] is not None for p in pages),
           "pages_unscored": sum(p["copy_scores"]["ai_slop"]["score"] is None for p in pages),
           "chrome_lines": sorted(shared)[:50], "skeleton_openings": sorted(common)[:50], "pages": []}
    for key in ("ai_slop", "marketing_bias"):
        by_type = {}
        for p in pages:
            by_type.setdefault((p.get("classification") or {}).get("label", "other"), []).append(p["copy_scores"][key]["score"])
        ranked = sorted((p for p in pages if p["copy_scores"][key]["score"] is not None), key=lambda p: -p["copy_scores"][key]["score"])
        out[key] = {**stats([p["copy_scores"][key]["score"] for p in pages]),
                    "by_page_type": {label: stats(values) for label, values in sorted(by_type.items())},
                    "top_pages": [{"url": p["url"], "score": p["copy_scores"][key]["score"],
                                   "top_signals": p["copy_scores"][key]["top_signals"]} for p in ranked[:10]]}
    out["pages"] = [{"url": p["url"], "words_scored": p["copy_scores"]["words_scored"],
                     "ai_slop": p["copy_scores"]["ai_slop"]["score"], "marketing_bias": p["copy_scores"]["marketing_bias"]["score"]}
                    for p in pages]
    out["limitations"] = ["English phrase lists and sentence statistics only; heuristic evidence, never proof of AI authorship",
                          "Marketing bias measures reliance on persuasion levers, not dishonesty: truthful loss aversion or authority can be good copy",
                          f"Lines shared by {int(CHROME_SHARE * 100)}%+ of pages are treated as navigation/footer and not scored"]
    return out
