"""First-party discovery with bounded sitemap-index traversal."""
import xml.etree.ElementTree as ET
from collections import deque

from .crawler import Robots, normalize, origin


def discover(client, url):
    start = normalize(url)
    scope = origin(start)
    robots_response = client.get(scope + "/robots.txt", allowed_origin=scope)
    robots = Robots(robots_response)
    client.policies[scope] = robots
    client.delays[scope] = robots.delay()
    sitemap_seeds = [scope + "/sitemap.xml"]
    if robots.available:
        for line in robots_response.body.splitlines():
            if line.lower().startswith("sitemap:"):
                try:
                    sitemap_seeds.append(normalize(line.split(":", 1)[1].strip(), start))
                except ValueError:
                    pass
    queue, seen = deque(sitemap_seeds), set()
    urls, records, skipped = [], [], []
    while queue and len(seen) < client.config.max_sitemaps:
        target = queue.popleft()
        if target in seen:
            continue
        seen.add(target)
        if origin(target) != scope or robots.allowed(target) is not True:
            skipped.append({"url": target, "reason": "external_origin_or_robots"})
            continue
        response = client.get(target, allowed_origin=scope)
        record = response.metadata()
        record["locs"] = []
        if response.status == 200 and not response.error and not response.truncated:
            try:
                root = ET.fromstring(response.body)
                root_type = root.tag.rsplit("}", 1)[-1]
                if root_type not in {"sitemapindex", "urlset"}:
                    raise ValueError("Not a sitemap index or URL set")
                record["type"] = root_type
                for element in root.iter():
                    if element.tag.rsplit("}", 1)[-1] != "loc" or not element.text:
                        continue
                    try:
                        candidate = normalize(element.text.strip(), target)
                    except ValueError:
                        continue
                    if len(record["locs"]) >= client.config.max_urls:
                        record["url_limit_reached"] = True
                        break
                    record["locs"].append(candidate)
                    if origin(candidate) != scope:
                        continue
                    if root_type == "sitemapindex":
                        if len(queue) < client.config.max_urls:
                            queue.append(candidate)
                    elif candidate not in urls and len(urls) < client.config.max_urls:
                        urls.append(candidate)
            except (ET.ParseError, ValueError) as exc:
                record["parse_error"] = str(exc)
        records.append(record)
    return {"input_url": start, "origin": scope, "robots": robots.record(),
            "sitemap": {"documents": records, "skipped": skipped, "limit_reached": bool(queue)},
            "sitemap_urls": urls}, robots
