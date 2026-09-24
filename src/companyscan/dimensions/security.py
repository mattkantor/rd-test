"""Security headers, mixed content and cookie flags from responses already captured by the crawl. No extra requests."""
from collections import Counter

HEADERS = ["strict-transport-security", "content-security-policy", "x-content-type-options",
           "referrer-policy", "permissions-policy"]


def collect(client, discovery, pages, brand):
    rows, missing = [], Counter()
    for p in (p for p in pages if p.get("status") and p["status"] < 400):
        headers, https = p.get("headers", {}), p["url"].startswith("https://")
        absent = [h for h in HEADERS if h not in headers and (https or h != "strict-transport-security")]
        if "x-frame-options" not in headers and "frame-ancestors" not in headers.get("content-security-policy", ""):
            absent.append("x-frame-options/frame-ancestors")
        mixed = [u for u in p.get("script_sources", []) + [i["url"] or "" for i in p.get("images", [])] if https and u.startswith("http://")]
        # ponytail: headers dict keeps one Set-Cookie per response; multi-cookie responses are under-reported.
        cookie = headers.get("set-cookie")
        cookie_flags = None if not cookie else {flag: flag.lower() in cookie.lower() for flag in ("Secure", "HttpOnly", "SameSite")}
        missing.update(absent)
        rows.append({"url": p["url"], "https": https, "missing_headers": absent, "mixed_content": mixed[:20],
                     "cookie_flags": cookie_flags, "server": headers.get("server"), "powered_by": headers.get("x-powered-by")})
    return {"pages_checked": len(rows), "https": all(r["https"] for r in rows) if rows else None,
            "missing_summary": [{"header": h, "pages": n} for h, n in missing.most_common()],
            "pages": rows, "retrieved_from": "page response headers captured during the crawl",
            "limitation": "Response headers and server HTML only. No TLS/certificate, vulnerability, CMS-version or authenticated testing."}
