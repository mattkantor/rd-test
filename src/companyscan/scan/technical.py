"""Technical observations, never claims about actual AI visibility."""
from collections import Counter

from .crawler import origin
from .measurement import summarize
from .schema import site_entities

AI_AGENTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot", "PerplexityBot", "Google-Extended"]


def reports(client, discovery, robots, pages):
    scope = discovery["origin"]
    llms_url = scope + "/llms.txt"
    llms = client.get(llms_url, allowed_origin=scope) if robots.allowed(llms_url) is True else None
    access = []
    targets = list(dict.fromkeys([discovery["input_url"]] + [p["url"] for p in pages]))
    for agent in AI_AGENTS:
        access.append({"agent": agent, "kind": "EXTRACTED", "urls": [
            {"url": url, "robots_allowed": robots.allowed(url, agent),
             "status": "UNKNOWN" if robots.allowed(url, agent) is None else "PASS" if robots.allowed(url, agent) else "FAIL"}
            for url in targets]})
    indexing = []
    for p in pages:
        directives = list(p.get("robots_meta", {}).values()) + [p.get("headers", {}).get("x-robots-tag", "")]
        tokens = " ".join(directives).lower().replace(",", " ").split()
        indexing.append({"url": p["url"], "status": p["status"], "canonical_url": p.get("canonical_url"),
                         "robots_meta": p.get("robots_meta", {}), "x_robots_tag": p.get("headers", {}).get("x-robots-tag"),
                         "noindex_observed": bool({"noindex", "none"} & set(tokens)),
                         "extracted_characters": len(p.get("visible_text", "")),
                         "extractability": "UNKNOWN" if "visible_text" not in p else "WARNING" if len(p["visible_text"]) < 200 else "PASS",
                         "note": "Heuristic HTML text check; does not test JavaScript rendering or search indexing."})
    return {"robots": discovery["robots"], "sitemap": discovery["sitemap"],
            "crawler-access": {"robots_source": scope + "/robots.txt", "checks": access,
                               "limitation": "robots.txt policy only; bot-specific HTTP access, indexing and AI inclusion are UNKNOWN."},
            "schema": [{"url": p["url"], **p.get("json_ld", {"documents": [], "types": [], "errors": [], "status": "UNKNOWN"})} for p in pages],
            "redirects": [{"url": r.url, "final_url": r.final_url, "chain": r.redirects, "error": r.error} for r in client.cache.values() if r.redirects],
            "headers": [{"url": r.url, "status": r.status, "headers": r.headers} for r in client.cache.values()],
            "indexing": indexing,
            "llms": ({**llms.metadata(), "text": llms.body} if llms else {"url": llms_url, "status": "UNKNOWN", "reason": "robots_disallowed_or_unknown"}) | {"note": "Presence of llms.txt is not proof of AI visibility."},
            "feeds": [{"source": p["url"], **feed} for p in pages for feed in p.get("feeds", [])],
            "measurement": summarize(pages),
            "aeo": aeo(pages),
            "social-preview": social_preview(pages)}


def aeo(pages):
    ok = [p for p in pages if "json_ld" in p]
    issues = [dict(i, url=p["url"]) for p in ok for i in p["json_ld"].get("issues", [])]
    # Count pages affected, not occurrences.
    by_code = Counter(k[1:] for k in {(i["url"], i["severity"], i["code"], i.get("type"), i.get("property")) for i in issues})
    types = Counter(t for p in ok for t in p["json_ld"].get("types", []))
    return {"pages_checked": len(ok), "pages_with_json_ld": sum(bool(p["json_ld"]["documents"]) for p in ok),
            "pages_with_syntax_errors": [p["url"] for p in ok if p["json_ld"].get("errors")],
            "types": dict(types.most_common()),
            "issue_summary": [{"severity": k[0], "code": k[1], "type": k[2], "property": k[3], "pages": n} for k, n in by_code.most_common()],
            "entities": site_entities(ok), "issues": issues[:500],
            "limitation": "Checks JSON syntax, common rich-result properties, FAQ visibility and @id consistency. It is not Google's Rich Results Test and does not prove eligibility, indexing or AI citation."}


PREVIEW_REQUIRED = ["og:title", "og:description", "og:image", "og:url", "og:type"]


def social_preview(pages):
    rows, counts = [], Counter()
    for p in (p for p in pages if "social_meta" in p):
        m, found = p["social_meta"], []
        for key in PREVIEW_REQUIRED:
            if not m.get(key):
                found.append({"severity": "error" if key in {"og:title", "og:image"} else "warning", "code": "missing", "tag": key})
        if not m.get("twitter:card"):
            found.append({"severity": "warning", "code": "missing", "tag": "twitter:card",
                          "note": "X falls back to og: tags but shows a small card without twitter:card=summary_large_image"})
        image = m.get("og:image") or ""
        if image and not image.startswith("https://"):
            found.append({"severity": "error", "code": "image_not_absolute_https", "tag": "og:image"})
        if image and not (m.get("og:image:width") and m.get("og:image:height")):
            found.append({"severity": "warning", "code": "image_dimensions_missing", "tag": "og:image:width/height"})
        if m.get("og:url") and p.get("canonical_url") and m["og:url"].rstrip("/") != p["canonical_url"].rstrip("/"):
            found.append({"severity": "warning", "code": "og_url_not_canonical", "tag": "og:url"})
        if len(m.get("og:title") or "") > 90:
            found.append({"severity": "warning", "code": "title_may_truncate", "tag": "og:title"})
        if len(m.get("og:description") or "") > 200:
            found.append({"severity": "warning", "code": "description_may_truncate", "tag": "og:description"})
        counts.update((f["severity"], f["code"], f["tag"]) for f in found)
        rows.append({"url": p["url"], "tags": m, "icons": p.get("icons", []), "issues": found})
    images = Counter(r["tags"].get("og:image") for r in rows if r["tags"].get("og:image"))
    return {"pages_checked": len(rows),
            "issue_summary": [{"severity": k[0], "code": k[1], "tag": k[2], "pages": n} for k, n in counts.most_common()],
            "most_used_images": [{"url": u, "pages": n} for u, n in images.most_common(5)],
            "pages": rows,
            "limitation": "Tag presence and format only. Preview images are not fetched, so image reachability and size are UNKNOWN; each platform renders previews differently."}
