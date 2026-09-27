"""Customer-facing scorecard: one page per bundle, built from the newest analysis.json with no LLM call.

Each area of the analysis gets a 0-100 score from its findings (PASS 1, WARNING 0.5, FAIL 0; UNKNOWN left out) or, with
none, from its verdict; the overall score is the mean of the areas that could be scored. With the customer's lifetime
value and the new customers they want, the growth goal is priced and the estimated value at risk is the goal times the
overall score gap, split across areas by their gaps. Scores and dollars are estimates derived from verdicts, never proof."""
from pathlib import Path
from urllib.parse import urlparse

from .analyze import latest
from .pdf import CSS, LABELS, chrome_path, esc, items, level, load, print_pdf

WEIGHT = {"PASS": 1, "LOW": 1, "INFO": 1, "WARNING": 0.5, "MEDIUM": 0.5, "FAIL": 0, "HIGH": 0}
# analysis.json keys that aren't areas.
NOT_AREAS = {"source_manifest", "coverage", "comprehension", "business_impact_summary"}
LABELS = {**LABELS, "copy": "Website copy", "technical_marketing": "Technical marketing", "security": "Security",
          "fonts": "Fonts", "citation_gap": "Cited by AI search", "website": "Website"}
COUNT_WORDS = {"FAIL": "failed", "WARNING": "warning", "PASS": "passed", "UNKNOWN": "unknown"}
ESTIMATE = ("Scores are 100 when every finding in an area passes, 50 when they are all warnings, 0 when they all fail. "
            "Value at risk is an estimate: your customer lifetime value times the new customers you want, times the "
            "overall score gap. It shows scale, not a forecast.")


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
                    "counts": counts(found), "summary": summary or first_issue(found)})
    website = [f for i, f in pool.items() if i not in claimed]
    if website:
        out.insert(0, {"key": "website", "label": LABELS["website"], "score": score(f.get("severity") for f in website),
                       "counts": counts(website), "summary": first_issue(website)})
    return out


def first_issue(findings):
    worst = sorted(findings, key=lambda f: WEIGHT.get(level(f.get("severity")), 2))
    return " ".join(str(worst[0].get(k)) for k in ("title", "interpretation") if worst and worst[0].get(k)) if worst else ""


def build(analysis, ltv=None, customers=None):
    """The scorecard as data: overall score, areas, and dollars when ltv and customers are both given."""
    rows = areas(analysis)
    scored = [a for a in rows if a["score"] is not None]
    overall = round(sum(a["score"] for a in scored) / len(scored)) if scored else None
    card = {"overall": overall, "areas": rows, "goal": None, "at_risk": None}
    if ltv and customers and overall is not None:
        card["goal"] = ltv * customers
        card["at_risk"] = round(card["goal"] * (100 - overall) / 100)
        gaps = sum(100 - a["score"] for a in scored)
        for a in scored:
            a["at_risk"] = round(card["at_risk"] * (100 - a["score"]) / gaps) if gaps else 0
    impact = analysis.get("business_impact_summary") if isinstance(analysis.get("business_impact_summary"), dict) else {}
    by_id = {str(f.get("id")): f for f in items(analysis.get("findings"))}
    card["costliest"] = [str(by_id[str(i)]["business_impact"]["headline"]) for i in impact.get("ranked") or []
                         if isinstance(by_id.get(str(i), {}).get("business_impact"), dict)
                         and by_id[str(i)]["business_impact"].get("headline")][:3]
    return card


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
    weak = [a["label"] for a in sorted(scored, key=lambda a: a["score"]) if a["score"] < 50]
    text = f"We checked {len(card['areas'])} areas of how {host} shows up to buyers online and scored {len(scored)} of them. "
    text += (f"{len(weak)} need{'s' if len(weak) == 1 else ''} the most work: {', '.join(weak[:4])}"
             f"{' and others' if len(weak) > 4 else ''}. " if weak
             else "None scored below 50. ")
    if card["at_risk"] is not None:
        text += (f"Against a growth goal worth {money(card['goal'])}, the gaps put an estimated {money(card['at_risk'])} "
                 "at risk.")
    return text


def html(card, host, captured):
    tile = lambda a: (f'<div class="tile s-{band(a["score"])}"><span class="tile-label">{esc(a["label"])}</span>'
                      f'<b class="score">{esc(a["score"]) if a["score"] is not None else "—"}</b>'
                      + (f'<span class="risk">{money(a["at_risk"])} at risk</span>' if a.get("at_risk") else "")
                      + (f'<span class="counts">{" · ".join(f"{n} {COUNT_WORDS[k]}{"s" if n != 1 and k == "WARNING" else ""}" for k, n in a["counts"].items())}</span>' if a["counts"] else "")
                      + f'<p>{esc(clip(a["summary"]))}</p></div>')
    money_row = (f'<div class="money"><div><b>{money(card["goal"])}</b>Growth goal value</div>'
                 f'<div class="s-FAIL"><b>{money(card["at_risk"])}</b>Estimated at risk</div></div>' if card["at_risk"] is not None else
                 '<p class="note">Add customer lifetime value and new customers wanted to the site profile to see the dollar value.</p>')
    costliest = "".join(f"<li>{esc(c)}</li>" for c in card["costliest"])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(host)} scorecard</title>'
            f'<style>{CSS.read_text(encoding="utf-8")}</style></head><body class="designed scorecard">'
            f'<section class="cover"><div class="eyebrow">Online presence scorecard</div><div class="cover-title">{esc(host)}</div>'
            f'<p class="meta">Captured {esc(captured[:10])}</p><div class="overall s-{band(card["overall"])}">'
            f'<b>{esc(card["overall"]) if card["overall"] is not None else "—"}</b><span>Overall score</span></div></section>'
            f'<h2>Overview</h2><p>{esc(overview(card, host))}</p>{money_row}'
            + (f'<h4>Costliest issues</h4><ol class="costliest">{costliest}</ol>' if costliest else "")
            + f'<h2>By area</h2><div class="tiles">{"".join(tile(a) for a in card["areas"])}</div>'
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
    page.write_text(html(build(analysis, ltv, customers), host, str(manifest.get("created_at") or "")), encoding="utf-8")
    print_pdf(chrome, page, pdf)
    return pdf
