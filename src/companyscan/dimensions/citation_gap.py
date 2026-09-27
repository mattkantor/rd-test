"""Citation gap: the pages AI search cites when buyers ask about this market, and whether each one mentions the business.

Reads technical/ai_search.json from the same run (cli.run hands dimensions the ones collected before them), fetches each
cited third-party page once with the crawl's client, and matches its text and links against the identity profile with
plain string checks. No LLM."""
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..scan.crawler import Robots, origin
from ..scan.extract import extract
from .identity import host

MAX_PAGES = 40  # ponytail: most-cited first; raise if a market cites a long tail worth checking.
WORKERS = 6
LIMITATIONS = [
    "Cited pages come from one AI search run: one engine, one date, one searcher location; other runs cite other pages",
    f"Only the {MAX_PAGES} most-cited pages are fetched; the rest are listed as not_checked",
    "Pages are fetched once as server HTML with no JavaScript; many sites block automated requests, so unreachable and "
    "blocked_by_robots pages say nothing about whether the business is mentioned",
    "A mention is a literal match of the domain, an official profile link, a business name or a person's name; "
    "name_only matches may be a namesake, and a mention can be negative",
    "not_mentioned means none of the fingerprint's terms appear in the fetched text, not that the page is irrelevant",
]


def clean_url(url):
    """Drop tracking parameters (the engine adds utm_source=openai) and fragments, so one page cited twice counts once."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit(parts._replace(query=urlencode(query), fragment=""))


def page_key(url):
    """Host without www. plus path, lowercased: compares https://www.x.com/in/a/ with http://x.com/in/a."""
    return host(url) + urlsplit(url).path.rstrip("/").lower() if isinstance(url, str) else ""


def cited_pages(answers):
    """Every page the buyer answers cite, most answers first; each with the questions that led to it."""
    pages = {}
    for i, answer in enumerate(answers if isinstance(answers, list) else []):
        for source in (answer.get("sources") or []) if isinstance(answer, dict) else []:
            url = source.get("url") if isinstance(source, dict) else None
            if not (isinstance(url, str) and url.startswith(("http://", "https://")) and host(url)):
                continue
            url = clean_url(url)
            row = pages.setdefault(url, {"url": url, "domain": host(url), "title": source.get("title"), "citations": 0,
                                         "answers": set(), "prompts": []})
            row["citations"] += 1
            row["answers"].add(i)
            if isinstance(answer.get("prompt"), str) and answer["prompt"] not in row["prompts"]:
                row["prompts"].append(answer["prompt"])
    rows = sorted(pages.values(), key=lambda r: (-len(r["answers"]), -r["citations"], r["url"]))
    for row in rows:
        row["answers"] = len(row["answers"])
    return rows


def owned(url, profile):
    domain = profile.get("domain") or ""
    if domain and (host(url) == domain or host(url).endswith("." + domain)):
        return True
    return any(page_key(url).startswith(page_key(p)) for p in profile.get("profiles") or [] if page_key(p))


def matches(text, links, profile):
    """Which fingerprint terms the page shows: links to the site or an official profile, the domain, names, people."""
    domain, found = profile.get("domain") or "", []
    urls = [l["url"] for l in links if isinstance(l, dict) and isinstance(l.get("url"), str)]
    if domain and any(host(u) == domain or host(u).endswith("." + domain) for u in urls):
        found.append({"by": "link", "term": domain})
    elif domain and domain in text.lower():
        found.append({"by": "domain", "term": domain})
    for p in profile.get("profiles") or []:
        if page_key(p) and any(page_key(u).startswith(page_key(p)) for u in urls):
            found.append({"by": "profile", "term": p})
    for by, key in (("name", "names"), ("person", "people")):
        for term in profile.get(key) or []:
            if isinstance(term, str) and len(term.strip()) >= 3 and re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", text, re.I):
                found.append({"by": by, "term": term.strip()})
    return found


def snippet(text, found, width=120):
    """Text around the first matched name, person or domain: the quote a reader can check."""
    for item in found:
        if item["by"] in ("name", "person", "domain"):
            m = re.search(re.escape(item["term"]), text, re.I)
            if m:
                return " ".join(text[max(0, m.start() - width):m.end() + width].split())
    return None


def check(client, row, profile, robots):
    """Fetch one cited page and record whether it mentions the business."""
    key = origin(row["url"])
    if key not in robots:  # A race between workers only repeats a cached fetch.
        # ponytail: checks the cited URL only, not redirect targets; Client.policies would block redirects on sites
        # whose robots.txt is unreadable, which is most bot-walled sites.
        robots[key] = Robots(client.get(key + "/robots.txt"))
    if robots[key].allowed(row["url"]) is False:
        return {**row, "status": "blocked_by_robots"}
    response = client.get(row["url"])
    kind = (response.headers.get("content-type") or "").lower()
    if response.error or not response.status or response.status >= 400:
        return {**row, "status": "unreachable", "error": response.error or f"HTTP {response.status}"}
    if "html" in kind or not kind:
        page = extract(response.body, response.final_url)
        text, links = page["visible_text"], page["links"]
        row = {**row, "page_title": page["title"] or None}
    elif kind.startswith("text/"):
        text, links = response.body, []
    else:
        return {**row, "status": "unreadable", "error": f"content type {kind.split(';')[0]}"}
    found = matches(text, links, profile)
    strong = any(f["by"] in ("link", "domain", "profile") for f in found)
    return {**row, "final_url": response.final_url, "retrieved_at": response.retrieved_at,
            "status": "mentioned" if found else "not_mentioned", "match": ("strong" if strong else "name_only") if found else None,
            "matched": found, "snippet": snippet(text, found)}


def collect(client, discovery, pages, brand):
    source = (getattr(client, "technical", None) or {}).get("ai_search")
    if not isinstance(source, dict) or source.get("status") == "UNKNOWN":
        return {"status": "UNKNOWN", "reason": "ai_search_not_collected",
                "error": "citation_gap reads the cited sources from ai_search in the same run; collect ai_search too",
                "limitations": LIMITATIONS}
    profile = source.get("profile") if isinstance(source.get("profile"), dict) else {"domain": host(discovery["origin"])}
    rows = cited_pages(source.get("answers"))
    mine = [{**r, "status": "owned"} for r in rows if owned(r["url"], profile)]
    others = [r for r in rows if not owned(r["url"], profile)]
    robots, done = {}, 0
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(check, client, r, profile, robots) for r in others[:MAX_PAGES]]
        checked = []
        for future in futures:  # Input order; progress counts as each finishes in turn.
            checked.append(future.result())
            done += 1
            client.progress(done, len(futures), "cited pages")
    checked += [{**r, "status": "not_checked"} for r in others[MAX_PAGES:]]
    counts = Counter(r["status"] for r in checked + mine)
    domains = {}
    for r in checked:
        d = domains.setdefault(r["domain"], {"domain": r["domain"], "pages": 0, "citations": 0, "statuses": Counter()})
        d["pages"] += 1
        d["citations"] += r["citations"]
        d["statuses"][r["status"]] += 1
    for d in domains.values():
        s = d.pop("statuses")
        d["mentioned"] = True if s["mentioned"] else False if s["not_mentioned"] else None
    return {"status": "PARTIAL" if counts["unreachable"] or counts["blocked_by_robots"] else "COMPLETE",
            "source": "technical/ai_search.json",
            "fingerprint": {key: profile.get(key) or [] for key in ("names", "people", "profiles")} | {"domain": profile.get("domain")},
            "summary": {"cited_pages": len(rows), "owned": len(mine), "third_party": len(others),
                        **{s: counts[s] for s in ("mentioned", "not_mentioned", "unreachable", "blocked_by_robots",
                                                   "unreadable", "not_checked")},
                        "mentioned_name_only": sum(1 for r in checked if r.get("match") == "name_only")},
            "domains": sorted(domains.values(), key=lambda d: (-d["citations"], d["domain"])),
            "pages": mine + checked, "limitations": LIMITATIONS}
