"""Designed PDF: analysis.json laid out as scorecard/cards + report.md appendix (pandoc), styled by
views/report/report.css, printed by headless Chrome. Without analysis.json it prints report.md alone."""
import html as htmllib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from .analyze import latest

CSS = Path(__file__).resolve().parents[1] / "views" / "report" / "report.css"
CHROMES = [os.environ.get("CHROME", ""), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium", "google-chrome", "chromium", "chromium-browser"]
VERDICT = re.compile(r"(?<![\w-])(PASS|WARNING|FAIL|UNKNOWN|HIGH|MEDIUM|LOW)(?![\w-])")


def badges(html):
    """Wrap verdict/severity words in body text nodes so the stylesheet can colour them."""
    head, sep, body = html.partition("<body")
    if not sep:  # A fragment: all of it is body.
        head, body = "", head
    body = re.sub(r">([^<]+)<", lambda m: ">" + VERDICT.sub(r'<span class="v v-\1">\1</span>', m.group(1)) + "<", body)
    return head + sep + body


def render_pdf(bundle):
    bundle = Path(bundle).resolve()  # Chrome needs an absolute file:// URI.
    md = latest(bundle, "report.md")
    if not md:
        raise ValueError(f"No analysis/report.md in {bundle}; generate the report first")
    chrome = next((c for c in CHROMES if c and (Path(c).is_file() or shutil.which(c))), None)
    if not shutil.which("pandoc") or not chrome:
        raise ValueError("PDF rendering needs pandoc and Chrome/Chromium (set CHROME=/path/to/chrome)")
    title = next((line[2:].strip() for line in md.read_text(encoding="utf-8").splitlines() if line.startswith("# ")), "Report")
    html, pdf = md.with_suffix(".html"), md.with_suffix(".pdf")
    analysis = load(md.parent / "analysis.json")
    try:
        subprocess.run(["pandoc", str(md), "-s", "--embed-resources", "--css", str(CSS), "--metadata", f"pagetitle={title}",
                        *(["--shift-heading-level-by=1"] if analysis else []), "-o", str(html)],
                       check=True, capture_output=True, timeout=120)
        page = html.read_text(encoding="utf-8")
        page = designed(page, analysis, load(bundle / "manifest.json") or {}, title) if analysis else badges(page)
        html.write_text(page, encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"pandoc failed: {exc.stderr.decode('utf-8', 'replace')[-500:]}") from None
    except subprocess.TimeoutExpired:
        raise ValueError("pandoc timed out") from None
    print_pdf(chrome, html, pdf)
    return pdf


def load(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# Layout from analysis.json. Every field is model-written: escape everything and tolerate any key being missing or odd.
RANK = {"FAIL": 0, "HIGH": 0, "WARNING": 1, "MEDIUM": 1, "UNKNOWN": 2, "INFO": 3, "LOW": 3, "PASS": 4}
LABELS = {"jev_copy": "Human voice", "aeo": "Answer engines", "llm_reputation": "AI reputation", "ai_search": "AI search", "answer_coverage": "Answer coverage", "practitioners": "Practitioner profiles", "google_business": "Google listing", "meta_ads": "Meta ads",
          "social_preview": "Social previews", "measurement": "Measurement"}


def esc(value):
    return htmllib.escape("" if value is None else str(value))


def items(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def level(value):
    word = str(value or "UNKNOWN").strip().upper()
    return word if word in RANK else "UNKNOWN"


def badge(value):
    return f'<span class="v v-{level(value)}">{level(value)}</span>'


def verdicts(analysis):
    """(label, verdict, summary) for each dimension that reports a verdict, one level of nesting deep."""
    for key, value in analysis.items():
        if not isinstance(value, dict):
            continue
        if "verdict" in value:
            yield LABELS.get(key, key.replace("_", " ").capitalize()), value["verdict"], value.get("summary")
        for sub, inner in value.items():
            if isinstance(inner, dict) and "verdict" in inner:
                yield LABELS.get(sub, sub.replace("_", " ").capitalize()), inner["verdict"], inner.get("summary")


def findings(analysis):
    """Top-level findings plus each dimension's, merged by id; top-level (the detailed ones) wins."""
    found = {}
    for group in [analysis.get("findings")] + [v.get("findings") for v in analysis.values() if isinstance(v, dict)]:
        for item in items(group):
            key = str(item.get("id") or item.get("title"))
            found[key] = {**item, **found.get(key, {})}
    return sorted(found.values(), key=lambda f: RANK[level(f.get("severity"))])


def card(f):
    impact = f.get("business_impact") if isinstance(f.get("business_impact"), dict) else {}
    rows = "".join(f"<dt>{name}</dt><dd>{esc(f[key])}</dd>" for name, key in
                   (("Observed", "observation"), ("What it means", "interpretation")) if f.get(key))
    evidence = "".join(f'<li><code>{esc(e.get("artifact"))}</code> {esc(str(e.get("quote") or e.get("locator") or "")[:180])}</li>'
                       for e in items(f.get("evidence"))[:2])
    confidence = f'Confidence: {esc(f["confidence"])}' if f.get("confidence") else ""
    return (f'<article class="card s-{level(f.get("severity"))}"><header>{badge(f.get("severity"))}'
            f'<span class="fid">{esc(f.get("id"))}</span><h3>{esc(f.get("title"))}</h3></header>'
            + (f'<p class="impact">{esc(impact["headline"])}</p>' if impact.get("headline") else "")
            + (f"<dl>{rows}</dl>" if rows else "")
            + (f'<footer><span>{confidence}</span><ul class="ev">{evidence}</ul></footer>' if confidence or evidence else "")
            + "</article>")


def percent(value):
    try:
        return max(0, min(100, round(float(value) * 100)))
    except (TypeError, ValueError):
        return None


def designed(page, analysis, manifest, title):
    head, _, rest = page.partition("<body")
    body = rest.partition(">")[2].rpartition("</body>")[0]
    found = findings(analysis)
    by_id = {str(f.get("id")): f for f in found}
    coverage = analysis.get("coverage") if isinstance(analysis.get("coverage"), dict) else {}
    website = coverage.get("website") if isinstance(coverage.get("website"), dict) else {}
    host = urlparse(str(manifest.get("input_url") or "")).hostname or title
    meta = " · ".join(esc(x) for x in (f"Captured {str(manifest.get('created_at', ''))[:10]}" if manifest.get("created_at") else "",
                                        f"{website['pages_captured']} pages" if website.get("pages_captured") else "",
                                        f"Analysed {str(analysis.get('analyzed_at', ''))[:10]}" if analysis.get("analyzed_at") else "") if x)
    counts = {}
    for f in found:
        counts[level(f.get("severity"))] = counts.get(level(f.get("severity")), 0) + 1
    tiles = "".join(f'<div class="tile s-{level(v)}"><span class="tile-label">{esc(name)}</span>{badge(v)}<p>{esc(summary)}</p></div>'
                    for name, v, summary in verdicts(analysis))
    tally = "".join(f'<div class="count s-{k}"><b>{counts[k]}</b>{k.capitalize()}</div>' for k in RANK if k in counts)
    out = [f'<section class="cover"><div class="eyebrow">Company footprint report</div><div class="cover-title">{esc(host)}</div>'
           f'<p class="meta">{meta}</p><div class="tally">{tally}</div></section>']
    if tiles:
        out.append(f'<h2>Scorecard</h2><div class="tiles">{tiles}</div>')

    summary = analysis.get("business_impact_summary") if isinstance(analysis.get("business_impact_summary"), dict) else {}
    ranked = [by_id[str(i)] for i in summary.get("ranked") or [] if str(i) in by_id][:6]
    if ranked:
        rows = []
        for f in ranked:
            impact = f.get("business_impact") if isinstance(f.get("business_impact"), dict) else {}
            rows.append(f'<li>{badge(f.get("severity"))}<div><b>{esc(f.get("title"))}</b>'
                        f'<span>{esc(impact.get("headline"))}</span></div><em>{esc(str(impact.get("loss_type") or "").replace("_", " "))}</em></li>')
        out.append(f'<h2>Where it matters most</h2><ol class="impacts">{"".join(rows)}</ol>')

    matrix = items(analysis.get("matrix"))
    if matrix:
        rows = "".join(f'<tr><td>{esc(m.get("dimension"))}</td><td>{badge(m.get("website"))}</td>'
                       f'<td>{badge(m.get("social"))}</td><td>{badge(m.get("combined"))}</td></tr>' for m in matrix)
        out.append('<h2>Can a buyer tell who you are?</h2><table class="matrix"><thead><tr><th>Question</th><th>Website</th>'
                   f'<th>Social</th><th>Combined</th></tr></thead><tbody>{rows}</tbody></table>')

    issues = [f for f in found if level(f.get("severity")) not in ("PASS", "LOW")]
    if issues:
        out.append(f'<section class="page"><h2>Issues</h2>{"".join(card(f) for f in issues)}</section>')
    working = [f for f in found if f not in issues]
    if working:
        rows = "".join(f'<li>{badge(f.get("severity"))}<span class="fid">{esc(f.get("id"))}</span>{esc(f.get("title"))}</li>' for f in working)
        out.append(f'<h2>What’s working</h2><ul class="working">{rows}</ul>')

    recs = items(analysis.get("recommendations"))
    if recs:
        rows = "".join(f'<tr><td>{badge(r.get("priority"))}</td><td>{esc(r.get("recommendation"))}</td>'
                       f'<td class="fid">{esc(", ".join(map(str, r.get("for_findings") or [])))}</td></tr>' for r in recs)
        out.append(f'<section class="page"><h2>Recommendations</h2><table class="recs"><thead><tr><th>Priority</th>'
                   f'<th>Recommendation</th><th>Fixes</th></tr></thead><tbody>{rows}</tbody></table></section>')

    for key in ("llm_reputation", "ai_search"):
        rep = analysis.get(key) if isinstance(analysis.get(key), dict) else None
        if not rep:
            continue
        bars = "".join(f'<div class="bar"><span>{name}</span><div class="track"><i style="width:{pct}%"></i></div><b>{pct}%</b></div>'
                       for name, pct in (("Mention rate", percent(rep.get("mention_rate"))), ("Share of voice", percent(rep.get("share_of_voice"))))
                       if pct is not None)
        rank = (f'<p class="rank">Rank <b>{esc(rep["rank"])}</b> of {esc(rep.get("of") or "?")}</p>' if rep.get("rank")
                else f'<p class="rank"><b>Not ranked</b> in {esc(rep.get("of") or "any")} assistant answers</p>')
        chips = lambda values: "".join(f"<span>{esc(c)}</span>" for c in (values if isinstance(values, list) else [])[:8] if isinstance(c, str))
        rivals, sources = chips(rep.get("top_competitors")), chips(rep.get("top_sources"))  # top_sources: ai_search only.
        out.append(f'<h2>{LABELS[key]}</h2><div class="rep">{rank}{bars}</div>'
                   + (f'<h4>Named instead of you</h4><div class="chips">{rivals}</div>' if rivals else "")
                   + (f'<h4>Sites the answers cite</h4><div class="chips">{sources}</div>' if sources else "")
                   + (f'<p>{esc(rep.get("summary"))}</p>' if rep.get("summary") else ""))

    limits = [x for x in (coverage.get("limitations") or []) + (website.get("notes") or []) if isinstance(x, str)]
    if limits:
        out.append(f'<h4>Coverage and limits</h4><ul class="limits">{"".join(f"<li>{esc(x)}</li>" for x in limits)}</ul>')
    out.append(f'<section class="page appendix"><h2>Full analysis</h2>{badges(body)}</section>')
    return f'{head}<body class="designed">{"".join(out)}</body></html>'


def print_pdf(chrome, html, pdf, timeout=180):
    # Headless Chrome on macOS can write the PDF and then never exit, so wait for a finished file, not the process.
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as profile:  # Separate profile so it doesn't attach to a running Chrome.
        proc = subprocess.Popen([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
                                 f"--print-to-pdf={pdf}", html.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline, size = time.monotonic() + timeout, -1
        try:
            while time.monotonic() < deadline:
                current = pdf.stat().st_size if pdf.exists() else -1
                if current > 0 and current == size:
                    return
                if proc.poll() is not None and current <= 0:
                    raise ValueError(f"Chrome exited ({proc.returncode}) without writing {pdf.name}")
                size = current
                time.sleep(1)
            raise ValueError("Chrome timed out printing the PDF")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
