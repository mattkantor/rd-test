"""Analytics, pixel and consent detection from server HTML. Presence is not proof a tag fires."""
import re

# (tool, category, pattern over script/iframe src and inline JS, optional id pattern)
SIGNATURES = [
    ("Google Tag Manager", "tag_manager", r"googletagmanager\.com/(?:gtm\.js|ns\.html)", r"\bGTM-[A-Z0-9]{4,}\b"),
    # G- is a GA4 stream; GT-/AW-/DC- tags route to destinations configured inside Google, not visible in HTML.
    ("Google tag (gtag.js)", "analytics", r"googletagmanager\.com/gtag/js|gtag\(\s*['\"]config['\"]", r"\b(?:G|GT|AW|DC)-[A-Z0-9]{6,}\b"),
    ("Google Site Kit (WordPress)", "analytics", r"google-site-kit/|_googlesitekit", None),
    ("Universal Analytics (retired)", "analytics", r"google-analytics\.com/(?:analytics|ga)\.js|\bUA-\d{4,}-\d+\b", r"\bUA-\d{4,}-\d+\b"),
    ("Google Ads", "ads_pixel", r"gtag/js\?id=AW-|['\"]AW-\d{6,}", r"\bAW-\d{6,}\b"),
    ("Meta Pixel", "ads_pixel", r"connect\.facebook\.net/[^\"']*/fbevents\.js|fbq\(\s*['\"]init['\"]", r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})"),
    ("LinkedIn Insight Tag", "ads_pixel", r"snap\.licdn\.com/li\.lms-analytics|_linkedin_partner_id", r"_linkedin_partner_id\s*=\s*['\"]?(\d{4,})"),
    ("X (Twitter) Pixel", "ads_pixel", r"static\.ads-twitter\.com/uwt\.js|twq\(\s*['\"]config", None),
    ("TikTok Pixel", "ads_pixel", r"analytics\.tiktok\.com/i18n/pixel", None),
    ("Microsoft UET (Bing Ads)", "ads_pixel", r"bat\.bing\.com/bat\.js", None),
    ("Microsoft Clarity", "session_recording", r"clarity\.ms/tag/|\(c,l,a,r,i,t,y\)", r"clarity\.ms/tag/([a-z0-9]{6,})"),
    ("Hotjar", "session_recording", r"static\.hotjar\.com|hotjar\.com/c/hotjar-", r"hjid\s*:\s*(\d{4,})"),
    ("HubSpot", "marketing_automation", r"js(?:-na1)?\.hs-scripts\.com|js\.hs-analytics\.net", r"hs-scripts\.com/(\d{4,})\.js"),
    ("Plausible", "analytics", r"plausible\.io/js/", None),
    ("Fathom", "analytics", r"cdn\.usefathom\.com", None),
    ("Matomo", "analytics", r"matomo\.js|piwik\.js|_paq\.push", None),
    ("PostHog", "analytics", r"posthog\.init|[a-z]+\.posthog\.com/static/array\.js", None),
    ("Segment", "analytics", r"cdn\.segment\.com/analytics\.js", None),
    ("Mixpanel", "analytics", r"cdn\.mxpnl\.com|mixpanel\.init", None),
    ("Heap", "analytics", r"cdn\.heapanalytics\.com|heap\.load\(", None),
    ("Amplitude", "analytics", r"cdn\.amplitude\.com|amplitude\.getInstance", None),
    ("Cloudflare Web Analytics", "analytics", r"static\.cloudflareinsights\.com/beacon", None),
    ("WordPress.com Stats (Jetpack)", "analytics", r"stats\.wp\.com/e-", None),
    ("Cookiebot", "consent", r"consent\.cookiebot\.com", None),
    ("OneTrust", "consent", r"cdn\.cookielaw\.org|otSDKStub", None),
    ("CookieYes", "consent", r"cdn-cookieyes\.com", None),
    ("Complianz", "consent", r"complianz", None),
    ("Termly", "consent", r"app\.termly\.io", None),
    ("iubenda", "consent", r"cdn\.iubenda\.com", None),
    ("Osano", "consent", r"cmp\.osano\.com", None),
]


def detect(srcs, inline):
    """Return one record per detected tool with the ids and evidence that matched."""
    found = []
    haystacks = [("src", s) for s in srcs] + [("inline", inline)]
    for tool, category, pattern, id_pattern in SIGNATURES:
        hits = [(kind, text) for kind, text in haystacks if text and re.search(pattern, text, re.I)]
        if not hits:
            continue
        ids = set()
        if id_pattern:
            for _, text in hits:
                for m in re.finditer(id_pattern, text):
                    ids.add(m.group(1) if m.groups() else m.group(0))
        kind, text = hits[0]
        m = re.search(pattern, text, re.I)
        snippet = text if kind == "src" else text[max(0, m.start() - 40):m.end() + 40]
        found.append({"tool": tool, "category": category, "ids": sorted(ids), "kind": "OBSERVED",
                      "evidence": {"source": kind, "match": re.sub(r"\s+", " ", snippet)[:200]}})
    return found


def summarize(pages):
    ok = [p for p in pages if "measurement" in p]
    tools = {}
    for p in ok:
        for t in p["measurement"]:
            rec = tools.setdefault(t["tool"], {"tool": t["tool"], "category": t["category"], "ids": set(), "pages": []})
            rec["ids"].update(t["ids"])
            rec["pages"].append(p["url"])
    rows = [{**r, "ids": sorted(r["ids"]), "pages_present": len(r["pages"]), "pages_total": len(ok),
             "missing_on": [p["url"] for p in ok if p["url"] not in r["pages"]][:50], "pages": r["pages"][:50]}
            for r in tools.values()]
    cats = {r["category"] for r in rows}
    return {"tools": rows, "pages_checked": len(ok),
            "has_measurement": bool(cats & {"analytics", "tag_manager", "marketing_automation"}),
            "has_consent_tool": "consent" in cats,
            "pages_without_any_measurement_count": len(bare := [p["url"] for p in ok if not any(t["category"] in {"analytics", "tag_manager", "marketing_automation"} for t in p["measurement"])]),
            "pages_without_any_measurement": bare[:50],
            "limitation": "Server HTML only. Tags injected at runtime (for example by Google Tag Manager or a consent tool) are not observed, and presence does not prove a tag fires or records data."}
