"""Bounded HTTP transport, URL normalization, and robots-aware crawl."""
import ipaddress
import re
import socket
import time
from collections import deque
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from ..models import Config, Response, USER_AGENT

EXCLUDED = re.compile(r"(?:^|/)(?:login|log-in|signin|sign-in|logout|cart|checkout|account|wp-admin|wp-login\.php)(?:/|$)", re.I)
BINARY = re.compile(r"\.(?:pdf|zip|png|jpe?g|gif|webp|svg|mp[34]|avi|css|js|ico|woff2?|ttf|gz|xml)$", re.I)


def normalize(url: str, base: str | None = None) -> str:
    if base:
        url = urljoin(base, url)
    elif "://" not in url:
        url = "https://" + url
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL must be an HTTP(S) URL without credentials")
    host = parsed.hostname.encode("idna").decode().lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port and (parsed.scheme.lower(), port) not in {("http", 80), ("https", 443)}:
        host += f":{port}"
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid", "msclkid"}]
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", urlencode(sorted(query)), ""))


def origin(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def crawlable(url: str) -> bool:
    p = urlsplit(url)
    return not p.query and not EXCLUDED.search(p.path) and not BINARY.search(p.path)


class Redirects(HTTPRedirectHandler):
    def __init__(self, client, chain, allowed_origin):
        self.client, self.chain, self.allowed_origin = client, chain, allowed_origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = normalize(newurl, req.full_url)
        self.chain.append({"from": req.full_url, "to": target, "status": code})
        self.client.check_target(target)
        if self.allowed_origin and origin(target) != self.allowed_origin:
            raise ValueError("redirect outside crawl origin")
        policy = self.client.policies.get(origin(target))
        if policy is not None and policy.allowed(target) is not True:
            raise ValueError("redirect target disallowed or unknown in robots.txt")
        if len(self.chain) > 10:
            raise ValueError("redirect limit exceeded")
        self.client.throttle(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


class Client:
    def __init__(self, config: Config):
        self.config = config
        self.cache: dict[str, Response] = {}
        self.last_request: dict[str, float] = {}
        self.delays: dict[str, float] = {}
        self.policies = {}
        # Set by cli.run for the web UI's progress bar; a no-op everywhere else.
        self.progress = lambda done=None, total=None, unit="": None

    def check_target(self, url: str) -> None:
        parsed = urlsplit(normalize(url))
        if self.config.allow_private:
            return
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
            raise ValueError("non-public target blocked (use --allow-private for trusted local fixtures)")

    def throttle(self, url: str) -> None:
        key = origin(url)
        wait = max(self.config.delay, self.delays.get(key, 0)) - (time.monotonic() - self.last_request.get(key, 0))
        if wait > 0:
            time.sleep(wait)
        self.last_request[key] = time.monotonic()

    def get(self, url: str, allowed_origin: str | None = None) -> Response:
        url = normalize(url)
        cache_key = (url, allowed_origin)
        if cache_key in self.cache:
            return self.cache[cache_key]
        result = Response(url=url, final_url=url)
        try:
            self.check_target(url)
            self.throttle(url)
            opener = build_opener(Redirects(self, result.redirects, allowed_origin))
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9", "Accept-Encoding": "identity"})
            try:
                stream = opener.open(request, timeout=self.config.timeout)
            except HTTPError as exc:
                stream = exc
            with stream:
                result.status = stream.code
                result.final_url = normalize(stream.geturl())
                result.headers = {k.lower(): v for k, v in stream.headers.items()}
                data = stream.read(self.config.max_bytes + 1)
                result.truncated = len(data) > self.config.max_bytes
                encoding = stream.headers.get_content_charset() or "utf-8"
                try:
                    result.body = data[:self.config.max_bytes].decode(encoding, errors="replace")
                except LookupError:
                    result.body = data[:self.config.max_bytes].decode("utf-8", errors="replace")
                if result.status >= 400:
                    result.error = f"HTTP {result.status}"
        except (OSError, URLError, ValueError) as exc:
            result.error = str(exc)
        self.cache[cache_key] = result
        return result


class Robots:
    def __init__(self, response: Response):
        self.response = response
        self.parser = RobotFileParser(response.url)
        self.available = response.status is not None and 200 <= response.status < 300 and not response.error and not response.truncated
        self.missing = response.status in {404, 410}
        self.parser.parse(response.body.splitlines() if self.available else [])

    def allowed(self, url: str, agent: str = USER_AGENT) -> bool | None:
        if self.missing:
            return True
        if not self.available:
            return None
        return self.parser.can_fetch(agent, url)

    def delay(self) -> float:
        return float(self.parser.crawl_delay(USER_AGENT) or self.parser.crawl_delay("*") or 0)

    def record(self) -> dict:
        return {**self.response.metadata(), "text": self.response.body, "policy_status": "OBSERVED" if self.available or self.missing else "UNKNOWN"}


def crawl(client: Client, start: str, robots: Robots, seeds: list[str]) -> tuple[list[dict], list[dict]]:
    from .extract import extract
    scope = origin(start)
    queue = deque([(start, 0)] + [(u, 1) for u in seeds if u != start])
    queued = {u for u, _ in queue}
    seen, canonicals = set(), set()
    pages, skipped = [], []
    while queue and len(pages) < client.config.max_pages:
        url, depth = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        reason = None
        if depth > client.config.max_depth:
            reason = "depth_limit"
        elif origin(url) != scope:
            reason = "external_origin"
        elif not crawlable(url):
            reason = "excluded_path_or_query"
        elif url in canonicals:
            reason = "duplicate_canonical"
        elif robots.allowed(url) is not True:
            reason = "robots_disallowed" if robots.allowed(url) is False else "robots_unknown"
        if reason:
            skipped.append({"url": url, "reason": reason})
            continue
        response = client.get(url, allowed_origin=scope)
        page = {**response.metadata(), "id": f"{len(pages) + 1:04d}", "depth": depth}
        if response.status is not None and 200 <= response.status < 300 and not response.error:
            mime = response.headers.get("content-type", "").lower()
            if "html" in mime or (not mime and response.body.lstrip().startswith("<")):
                page.update(extract(response.body, response.final_url))
                canonical = page.get("canonical_url")
                if canonical and origin(canonical) == scope:
                    if canonical in canonicals:
                        page["duplicate_of"] = canonical
                    canonicals.add(canonical)
                if depth < client.config.max_depth:
                    for link in page.get("links", []):
                        target = link["url"]
                        if origin(target) == scope and target not in queued and len(queued) < client.config.max_urls:
                            queued.add(target)
                            queue.append((target, depth + 1))
            else:
                page["extraction_status"] = "UNSUPPORTED_CONTENT_TYPE"
        pages.append(page)
        client.progress(len(pages), client.config.max_pages, "pages")
    skipped.extend({"url": u, "reason": "page_limit"} for u, _ in queue)
    return pages, skipped
