"""Declared font families from inline styles, same-origin stylesheets and Google/Adobe font URLs."""
import re
from collections import Counter
from urllib.parse import parse_qs, urlsplit

from ..scan.crawler import origin
from ..scan.extract import font_families


def collect(client, discovery, pages, brand, limit=20):
    scope, sheets = discovery["origin"], {}
    for url in dict.fromkeys(u for p in pages for u in p.get("stylesheets", [])):
        host = urlsplit(url).hostname or ""
        if host == "fonts.googleapis.com":
            families = [f.split(":")[0] for v in parse_qs(urlsplit(url).query).get("family", []) for f in v.split("|")]
            sheets[url] = {"url": url, "source": "Google Fonts", "families": sorted(set(families)), "status": "EXTRACTED_FROM_URL"}
        elif host == "use.typekit.net":
            sheets[url] = {"url": url, "source": "Adobe Fonts", "families": [], "status": "UNKNOWN", "note": "Kit contents not fetched"}
        elif origin(url) != scope:
            sheets[url] = {"url": url, "source": "third-party", "families": [], "status": "NOT_FETCHED"}
        elif len([s for s in sheets.values() if s["source"] == "first-party"]) >= limit or client.policies[scope].allowed(url) is not True:
            sheets[url] = {"url": url, "source": "first-party", "families": [], "status": "NOT_FETCHED"}
        else:
            r = client.get(url, allowed_origin=scope)
            ok = r.status == 200 and not r.error
            sheets[url] = {"url": url, "source": "first-party", "status": r.status, "error": r.error, "truncated": r.truncated,
                           "families": font_families(r.body) if ok else [],
                           "font_faces": font_families(" ".join(re.findall(r"@font-face\s*\{([^}]*)\}", r.body, re.I))) if ok else []}
    site, rows = Counter(), []
    for p in (p for p in pages if "stylesheets" in p):
        families = set(p.get("inline_font_families", []))
        for url in p["stylesheets"]:
            families.update(sheets[url]["families"])
        site.update(families)
        rows.append({"url": p["url"], "families": sorted(families)})
    return {"pages_checked": len(rows), "distinct_families": len(site),
            "families": [{"family": f, "pages": n} for f, n in site.most_common()],
            "stylesheets": list(sheets.values()), "pages": rows,
            "limitation": "Declared fonts from HTML and same-origin CSS only; computed/rendered fonts, JS-injected styles and `font:` shorthand are not evaluated."}
