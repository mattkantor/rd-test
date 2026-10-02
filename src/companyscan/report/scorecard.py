"""Customer-facing scorecard: one page per bundle, built from the newest analysis.json with no LLM call.

Each area of the analysis gets a 0-100 score from its findings (PASS 1, WARNING 0.5, FAIL 0; UNKNOWN left out) or, with
none, from its verdict; the overall score is the mean of the areas that could be scored. With the customer's lifetime
value and the new customers they want, the growth goal is priced and the estimated value at risk is the goal times the
overall score gap, split across areas by their gaps. Scores and dollars are estimates derived from verdicts, never proof.

The loss story comes from the report's business_impact on each finding (who is lost and how) and the fixes from its
recommendations; the service pitch and call to action come from COMPANYSCAN_SERVICE_* settings (service())."""
import os
from pathlib import Path
from urllib.parse import urlparse

from .analyze import hidden, latest
from .pdf import CSS, LABELS, chrome_path, esc, items, level, load, print_pdf

WEIGHT = {"PASS": 1, "LOW": 1, "INFO": 1, "WARNING": 0.5, "MEDIUM": 0.5, "FAIL": 0, "HIGH": 0}
# analysis.json keys that aren't areas.
NOT_AREAS = {"source_manifest", "coverage", "comprehension", "business_impact_summary"}
LABELS = {**LABELS, "copy": "Website copy", "technical_marketing": "Technical marketing", "security": "Security",
          "fonts": "Fonts", "citation_gap": "Cited by AI search", "website": "Website"}
# business-impact.md loss types, said from the owner's side.
LOSS_WORDS = {"leads": "Enquiries you never get", "conversions": "Interested buyers who don't book", "deal_value": "Deals that close smaller",
              "sales_cycle": "Deals that stall", "trust": "Buyers who doubt you", "visibility": "Buyers who never find you",
              "wasted_effort": "Marketing spend that returns nothing"}
# Why each area matters to a business owner: shown on every area, even one the report says little about, so the
# customer sees what a weak score means for them. Plain claims about how buyers behave, no statistics.
WHY = {
    "website": "Your website is where buyers decide whether to contact you. If it's unclear who you help, what you do "
               "or how to get started, ready buyers leave for a competitor who makes it obvious.",
    "copy": "Your words do the selling when you're not in the room. Copy that speaks to your buyer's problem gets "
            "enquiries; generic copy blends in with every competitor.",
    "jev_copy": "Buyers are getting good at spotting generic, machine-written copy, and they trust it less. Copy that "
                "sounds like you makes them believe you.",
    "technical_marketing": "Tracking, structured data and link previews decide whether you can see what's working, "
                           "whether search and AI tools understand your pages, and how your links look when shared.",
    "fonts": "Inconsistent type makes a site feel stitched together. Buyers read that as less established and less "
             "trustworthy, even if they can't say why.",
    "security": "Security settings protect your visitors and signal that you're a careful operator. Larger buyers "
                "increasingly check this before they sign.",
    "practitioners": "People buy from people. When your experts have clear profiles, buyers, search engines and AI "
                     "assistants can find them and trust what they say.",
    "google_business": "Your Google listing is often the first thing a local buyer sees, before your website. Wrong "
                       "details or a thin listing send them to the business next door.",
    "meta_ads": "Ads on Facebook and Instagram reach buyers before they start searching. If you're not there, your "
                "competitors meet them first.",
    "llm_reputation": "More buyers now ask AI assistants for a shortlist before they search. If the assistant doesn't "
                      "know you, you're not on the list.",
    "ai_search": "AI search tools answer buyers' questions with a few recommended names and links. Those names get the "
                 "calls; everyone else is invisible.",
    "citation_gap": "AI tools recommend businesses that trusted third-party sites mention. If those pages talk about your "
                    "competitors and not you, the AI will too.",
    "answer_coverage": "Buyers ask about cost, timing and fit before they call. If your site doesn't answer, they ask "
                       "someone else's site, or an AI that quotes a competitor.",
}
WHY["analytics"] = ("Analytics is how you know who visits, where they came from and what makes them get in touch. "
                    "Without it you can't tell which marketing works, so every decision is a guess.")
WHY_DEFAULT = "This is part of how buyers find, judge and choose a business like yours online."
COUNT_WORDS = {"FAIL": "failed", "WARNING": "warning", "PASS": "passed", "UNKNOWN": "unknown"}
ESTIMATE = ("Scores are 100 when every finding in an area passes, 50 when they are all warnings, 0 when they all fail. "
            "Value at risk is an estimate: your customer lifetime value times the new customers you want, times the "
            "overall score gap. It shows scale, not a forecast. The monthly figure assumes the goal is for one year.")


def service():
    """Who fixes it, from COMPANYSCAN_SERVICE_NAME/_PITCH/_CTA. The defaults are draft copy: set your own before sending."""
    return {"name": os.environ.get("COMPANYSCAN_SERVICE_NAME") or "Obvious Choice Systems",
            "pitch": os.environ.get("COMPANYSCAN_SERVICE_PITCH") or (
                "You don't have to fix any of this yourself. Obvious Choice Systems does the work for you: we fix the gaps that keep "
                "buyers and AI assistants from choosing you, in order of what they cost you, and re-scan so you can "
                "see each score move."),
            "cta": os.environ.get("COMPANYSCAN_SERVICE_CTA") or (
                "Reply to this email to book a 30-minute walkthrough of your scorecard and a fix plan for the areas "
                "costing you most.")}


def score(verdicts):
    weights = [WEIGHT[level(v)] for v in verdicts if level(v) in WEIGHT]
    return round(sum(weights) / len(weights) * 100) if weights else None


def counts(findings):
    found = {}
    for f in findings:
        found[level(f.get("severity"))] = found.get(level(f.get("severity")), 0) + 1
    return {k: found[k] for k in ("FAIL", "WARNING", "PASS", "UNKNOWN") if k in found}


def areas(analysis):
    """[{key, label, score, counts, summary}] for every area in the analysis, website first. An area lists its findings
    in full or as IDs of top-level findings; the top-level findings no area claims (the site itself, accessibility) make
    up the website area."""
    pool = {str(f.get("id")): f for f in items(analysis.get("findings"))}
    out, claimed = [], set()
    for key, value in analysis.items():
        if key in NOT_AREAS or not isinstance(value, dict):
            continue
        subs = {k: v for k, v in value.items() if isinstance(v, dict) and "verdict" in v}  # e.g. technical_marketing.aeo
        if "verdict" not in value and "findings" not in value and not subs:
            continue
        listed = value.get("findings") if isinstance(value.get("findings"), list) else []
        found = [pool.get(str(f)) if isinstance(f, (str, int)) else f for f in listed]
        found = [f for f in found if isinstance(f, dict)]
        claimed |= {str(f.get("id")) for f in found}
        verdicts = [f.get("severity") for f in found] or [value.get("verdict"), *(s.get("verdict") for s in subs.values())]
        summary = value.get("summary") if isinstance(value.get("summary"), str) else " ".join(
            s["summary"] if isinstance(s.get("summary"), str) else f"{k.replace('_', ' ').capitalize().replace('Icp', 'ICP')}: {level(s['verdict'])}."
            for k, s in subs.items())
        out.append({"key": key, "label": LABELS.get(key, key.replace("_", " ").capitalize()), "score": score(verdicts),
                    "counts": counts(found), "summary": summary or first_issue(found), "findings": found})
    website = [f for i, f in pool.items() if i not in claimed]
    if website:
        out.insert(0, {"key": "website", "label": LABELS["website"], "score": score(f.get("severity") for f in website),
                       "counts": counts(website), "summary": first_issue(website), "findings": website})
    return out


def sentences(*parts):
    """Join a headline and its explanation as sentences: headlines usually have no closing stop."""
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return " ".join(p if p[-1] in ".!?…" or p is parts[-1] else p + "." for p in parts)


def first_issue(findings):
    worst = sorted(findings, key=lambda f: WEIGHT.get(level(f.get("severity")), 2))
    return sentences(worst[0].get("title"), worst[0].get("interpretation")) if worst else ""


def analytics_area(measurement):
    """The Analytics area, scored from the scan's technical/measurement.json rather than the report: the share of pages
    with an analytics tool, tag manager or marketing-automation tag. None at all is a high risk: the business can't see
    its visitors. Server HTML only, so a tag added at runtime without a tag manager would be missed."""
    if not isinstance(measurement, dict) or not isinstance(measurement.get("pages_checked"), int) or measurement["pages_checked"] < 1:
        return None
    checked, bare = measurement["pages_checked"], measurement.get("pages_without_any_measurement_count")
    bare = bare if isinstance(bare, int) and 0 <= bare <= checked else 0
    tools = sorted({str(t.get("tool")) for t in measurement.get("tools") or [] if isinstance(t, dict)
                    and t.get("category") in ("analytics", "tag_manager", "marketing_automation")})
    area = {"key": "analytics", "label": "Analytics", "findings": [], "protects": False, "high_risk": False}
    if not measurement.get("has_measurement"):
        return {**area, "score": 0, "counts": {"FAIL": 1}, "high_risk": True,
                "summary": f"No analytics or tag manager was found on any of the {checked} pages checked.",
                "loss": {"headline": "You can't see who visits or what brings them in",
                         "mechanism": "Without analytics you can't tell which pages, channels or ads bring customers, so "
                                      "spend goes to guesses and problems go unnoticed until sales drop."},
                "fixes": ["Set up analytics on every page and track enquiries and bookings as conversions"]}
    if bare:
        return {**area, "score": round((checked - bare) / checked * 100), "counts": {"WARNING": 1},
                "summary": f"{', '.join(tools)} found, but {bare} of {checked} pages {'has' if bare == 1 else 'have'} no analytics tag.",
                "loss": {"headline": "Part of your site is invisible to your reporting",
                         "mechanism": "Visits to untagged pages don't show up, so your numbers undercount what's happening."},
                "fixes": ["Add the analytics tag to the pages missing it and check conversions are recorded"]}
    return {**area, "score": 100, "counts": {"PASS": 1},
            "summary": f"{', '.join(tools)} {'runs' if len(tools) == 1 else 'run'} on every page checked.",
            "loss": {}, "fixes": []}


def build(analysis, ltv=None, customers=None, hide=(), measurement=None):
    """The scorecard as data: overall score, areas, and dollars when ltv and customers are both given. hide: area keys
    to leave out (analyze.hidden: ads when the site has no ad pixel). measurement: technical/measurement.json, which
    adds the Analytics area (first when there is none at all)."""
    rows = [a for a in areas(analysis) if a["key"] not in hide]
    tracked = analytics_area(measurement)
    if tracked:
        rows.insert(0 if tracked["high_risk"] else len(rows), tracked)
    scored = [a for a in rows if a["score"] is not None]
    overall = round(sum(a["score"] for a in scored) / len(scored)) if scored else None
    card = {"overall": overall, "areas": rows, "goal": None, "at_risk": None}
    if ltv and customers and overall is not None:
        card["goal"] = ltv * customers
        card["at_risk"] = round(card["goal"] * (100 - overall) / 100)
        gaps = sum(100 - a["score"] for a in scored)
        for a in scored:
            a["at_risk"] = round(card["at_risk"] * (100 - a["score"]) / gaps) if gaps else 0
        card["monthly"] = round(card["at_risk"] / 12)
    plan = recommendations(analysis)
    for a in rows:
        if a["key"] == "analytics":  # Scored from the scan; its loss and fix are already set.
            continue
        ids = {str(f.get("id")) for f in a["findings"]}
        a["fixes"] = [text for text, fixes in plan if ids & fixes][:2]
        worst = sorted((f for f in a["findings"] if impact(f).get("headline")), key=lambda f: WEIGHT.get(level(f.get("severity")), 2))
        a["loss"] = impact(worst[0]) if worst else {}
        a["protects"] = bool(worst) and level(worst[0].get("severity")) in ("PASS", "LOW", "INFO")
    summary = analysis.get("business_impact_summary") if isinstance(analysis.get("business_impact_summary"), dict) else {}
    pool = {str(f.get("id")): f for f in items(analysis.get("findings"))}
    open_ = [f for f in pool.values() if level(f.get("severity")) not in ("PASS", "LOW", "INFO") and impact(f).get("headline")]
    ranked = [pool[str(i)] for i in summary.get("ranked") or [] if str(i) in pool and pool[str(i)] in open_] or \
        sorted(open_, key=lambda f: ({"high": 0, "medium": 1, "low": 2}.get(str(impact(f).get("magnitude")).lower(), 3)))
    card["losses"] = [impact(f) for f in ranked[:3]]
    if tracked and tracked["high_risk"]:  # Flying blind leads the list.
        card["losses"] = [{**tracked["loss"], "loss_type": "wasted_effort"}] + card["losses"][:2]
    types = {}
    for f in open_:
        word = LOSS_WORDS.get(str(impact(f).get("loss_type")))
        if word:
            types[word] = types.get(word, 0) + 1
    card["by_loss"] = sorted(types.items(), key=lambda t: -t[1])
    card["plan"] = [text for text, _ in plan][:3]
    return card


def impact(finding):
    return finding.get("business_impact") if isinstance(finding.get("business_impact"), dict) else {}


def recommendations(analysis):
    """[(text, finding IDs it fixes)] in the report's priority order; the rubric's and older field names both work."""
    out = []
    for r in items(analysis.get("recommendations")):
        text = r.get("recommendation") or r.get("summary")
        ids = r.get("for_findings") or r.get("rationale_findings") or []
        if isinstance(text, str) and text.strip():
            out.append((text.strip(), {str(i) for i in ids} if isinstance(ids, list) else set()))
    return out


def band(value):
    """Colour band for a score: the report's PASS/WARNING/FAIL accents."""
    return "UNKNOWN" if value is None else "PASS" if value >= 80 else "WARNING" if value >= 50 else "FAIL"


def clip(text, limit=320):
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def money(value):
    return f"${value:,.0f}"


def overview(card, host):
    scored = [a for a in card["areas"] if a["score"] is not None]
    if not scored:
        return f"The analysis of {host} had no areas with enough evidence to score."
    text = ""
    if any(a.get("high_risk") for a in card["areas"]):
        text += (f"High risk: {host} has no analytics, so there's no way to see who visits, where they come from or "
                 "what makes them get in touch. ")
    if card["at_risk"] is not None:
        text += (f"Right now, gaps in how {host} shows up to buyers online put an estimated {money(card['at_risk'])} of your "
                 f"{money(card['goal'])} growth goal at risk: about {money(card['monthly'])} for every month they stay open. ")
    weak = [a["label"] for a in sorted(scored, key=lambda a: a["score"]) if a["score"] < 50]
    text += f"We checked {len(card['areas'])} areas and scored {len(scored)} of them. "
    text += (f"{len(weak)} need{'s' if len(weak) == 1 else ''} the most work: {', '.join(weak[:4])}"
             f"{' and others' if len(weak) > 4 else ''}." if weak else "None scored below 50.")
    return text


def area_card(a):
    loss = a["loss"]
    rows = [("Why it matters", esc(WHY.get(a["key"], WHY_DEFAULT)))]
    if loss:
        rows.append(("What it protects" if a["protects"] else "Costing you", esc(sentences(loss.get("headline"), loss.get("mechanism")))))
    if a["fixes"]:
        rows.append(("We'll handle", "<ul>" + "".join(f"<li>{esc(clip(f, 220))}</li>" for f in a["fixes"]) + "</ul>"))
    tally = " · ".join(f"{n} {COUNT_WORDS[k]}{'s' if n != 1 and k == 'WARNING' else ''}" for k, n in a["counts"].items())
    return (f'<article class="area s-{band(a["score"])}"><div class="area-score"><b>{esc(a["score"]) if a["score"] is not None else "—"}</b>'
            + (f'<span class="risk">{money(a["at_risk"])} at risk</span>' if a.get("at_risk") else "")
            + f'</div><div><h3>{esc(a["label"])}' + (' <span class="flag">High risk</span>' if a.get("high_risk") else "")
            + '</h3>' + (f'<span class="counts">{tally}</span>' if tally else "")
            + f'<p>{esc(clip(a["summary"]))}</p>'
            + f'<dl>{"".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)}</dl></div></article>')


def html(card, host, captured):
    offer = service()
    money_row = (f'<div class="money"><div><b>{money(card["goal"])}</b>Your growth goal</div>'
                 f'<div class="s-FAIL"><b>{money(card["at_risk"])}</b>Estimated at risk</div>'
                 f'<div class="s-WARNING"><b>{money(card["monthly"])}</b>Each month it waits</div></div>' if card["at_risk"] is not None else
                 '<p class="note">Add customer lifetime value and new customers wanted per year to the site profile to see what this is costing.</p>')
    losses = "".join(f'<li><b>{esc(l.get("headline"))}</b>'
                     + (f'<span>{esc(l["who"])}: {esc(l.get("mechanism") or "")}</span>' if l.get("who") else
                        f'<span>{esc(l.get("mechanism") or "")}</span>')
                     + f'<em>{esc(LOSS_WORDS.get(str(l.get("loss_type")), ""))}</em></li>' for l in card["losses"])
    by_loss = "".join(f"<span>{esc(word)}: {n} issue{'s' if n != 1 else ''}</span>" for word, n in card["by_loss"])
    plan = "".join(f"<li>{esc(clip(p, 260))}</li>" for p in card["plan"])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(host)} scorecard</title>'
            f'<style>{CSS.read_text(encoding="utf-8")}</style></head><body class="designed scorecard">'
            f'<section class="cover"><div class="eyebrow">Online presence scorecard</div><div class="cover-title">{esc(host)}</div>'
            f'<p class="meta">Captured {esc(captured[:10])} · prepared by {esc(offer["name"])}</p><div class="overall s-{band(card["overall"])}">'
            f'<b>{esc(card["overall"]) if card["overall"] is not None else "—"}</b><span>Overall score</span></div></section>'
            f'<h2>What this is costing you</h2>{money_row}<p>{esc(overview(card, host))}</p>'
            + (f'<h4>Where you’re losing customers</h4><ol class="losses">{losses}</ol>' if losses else "")
            + (f'<div class="chips">{by_loss}</div>' if by_loss else "")
            + f'<section class="page"><h2>By area</h2>{"".join(area_card(a) for a in card["areas"])}</section>'
            f'<section class="fix"><h2>How {esc(offer["name"])} fixes this</h2><p>{esc(offer["pitch"])}</p>'
            + (f'<h4>What we’ll handle first</h4><ol class="plan">{plan}</ol>' if plan else "")
            + f'<p class="cta">{esc(offer["cta"])}</p></section>'
            f'<p class="note">{esc(ESTIMATE)}</p></body></html>')


def render_scorecard(bundle, ltv=None, customers=None):
    """Write analysis/.../scorecard.pdf beside the newest analysis.json and return its path."""
    bundle = Path(bundle).resolve()
    path = latest(bundle, "analysis.json")
    analysis = load(path) if path else None
    if not analysis:
        raise ValueError(f"No analysis/analysis.json in {bundle}; generate the report first")
    chrome = chrome_path()
    if not chrome:
        raise ValueError("PDF rendering needs Chrome/Chromium (set CHROME=/path/to/chrome)")
    manifest = load(bundle / "manifest.json") or {}
    host = urlparse(str(manifest.get("input_url") or "")).hostname or bundle.name
    page, pdf = path.parent / "scorecard.html", path.parent / "scorecard.pdf"
    card = build(analysis, ltv, customers, hidden(bundle), load(bundle / "technical/measurement.json"))
    page.write_text(html(card, host, str(manifest.get("created_at") or "")), encoding="utf-8")
    print_pdf(chrome, page, pdf)
    return pdf
