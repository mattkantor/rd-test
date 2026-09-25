"""Profile discovery is independent of optional public-HTML collection."""
from urllib.parse import urlsplit

from .crawler import Robots, normalize, origin
from .extract import extract
from .schema import entities

NETWORKS = {"linkedin.com": "linkedin", "instagram.com": "instagram", "facebook.com": "facebook",
            "youtube.com": "youtube", "youtu.be": "youtube", "x.com": "x", "twitter.com": "x",
            "tiktok.com": "tiktok", "github.com": "github", "g.page": "google-business",
            "maps.google.com": "google-business", "threads.net": "threads", "bsky.app": "bluesky",
            "pinterest.com": "pinterest", "medium.com": "medium", "substack.com": "substack",
            "beehiiv.com": "beehiiv", "ghost.io": "ghost", "hashnode.dev": "hashnode", "dev.to": "dev.to"}


def network(url):
    host = urlsplit(url).hostname or ""
    for domain, name in NETWORKS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def discover_profiles(pages, known=()):
    found = {}

    def add(url, source, method):
        try:
            url = normalize(url)
        except (ValueError, TypeError, AttributeError):
            return
        name = network(url)
        if not name:
            if method not in {"JSON-LD sameAs", "user-supplied"}:
                return
            name = "other"
        path = urlsplit(url).path.lower()
        if any(piece in path.split("/") for piece in {"share", "sharer", "sharer.php", "intent", "watch", "reel", "reels", "status", "posts", "p"}):
            return
        item = found.setdefault(url, {"network": name, "url": url, "official_confidence": 0,
                "verification_status": "unverified", "status": "DISCOVERED_NOT_COLLECTED",
                "profile": {"name": None, "description": None, "location": None}, "recent_content": [],
                "evidence": [], "retrieval": {"method": None, "retrieved_at": None}})
        confidence = {"JSON-LD sameAs": 0.9, "website-link": 0.75, "OpenGraph": 0.6, "user-supplied": 0.5}[method]
        item["official_confidence"] = max(item["official_confidence"], confidence)
        proof = {"source": source, "method": method, "kind": "OBSERVED" if method != "user-supplied" else "EXTRACTED"}
        if proof not in item["evidence"]:
            item["evidence"].append(proof)

    for page in pages:
        source = page["url"]
        for link in page.get("links", []):
            add(link["url"], source, "website-link")
        for obj in entities(page.get("json_ld", {}).get("documents", [])):
            values = obj.get("sameAs", [])
            for value in values if isinstance(values, list) else [values]:
                if isinstance(value, str):
                    add(value, source, "JSON-LD sameAs")
        for key, value in page.get("open_graph", {}).items():
            if key in {"og:see_also", "og:url"}:
                add(value, source, "OpenGraph")
    for url in known:
        add(url, "CLI --known-profile", "user-supplied")
    # A plain link only counts when it's the owner's: on the start page or in site-wide chrome. A case study linking a
    # client's LinkedIn from one page is about someone else.
    # ponytail: a third of pages approximates header/footer; parse <nav>/<footer> if owners hide profiles deeper.
    home = {p["url"] for p in pages if p.get("depth") == 0}
    chrome = max(2, len(pages) / 3)
    return sorted((p for p in found.values()
                   if any(e["method"] != "website-link" or e["source"] in home for e in p["evidence"])
                   or len(p["evidence"]) >= chrome), key=lambda p: (p["network"], p["url"]))


def collect_profiles(client, profiles):
    for item in profiles:
        url = item["url"]
        scope = origin(url)
        robots = Robots(client.get(scope + "/robots.txt", allowed_origin=scope))
        client.policies[scope] = robots
        client.delays[scope] = robots.delay()
        if robots.allowed(url) is not True:
            item["retrieval"]["error"] = "robots_disallowed_or_unknown"
            continue
        response = client.get(url, allowed_origin=scope)
        item["retrieval"] = {"method": "public-web", **response.metadata()}
        if response.status != 200 or response.error or "html" not in response.headers.get("content-type", "").lower():
            continue
        data = extract(response.body, response.final_url)
        # A 200 response can still be a login or anti-bot interstitial. Preserve
        # the capture without asserting that its title describes the company.
        item["status"] = "PUBLIC_HTML_CAPTURED_UNVERIFIED"
        item["captured_page"] = data
        item["collection_note"] = "Profile identity and content require review; may be a login/challenge page. Recent posts are not collected in V1."
    return profiles
