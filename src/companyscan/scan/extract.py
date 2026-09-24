"""HTML evidence extraction and transparent page classification heuristics."""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .crawler import normalize
from .measurement import detect
from .accessibility import check_html
from .schema import objects, parse_jsonld, validate


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


class Parser(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.stack = []
        self.text = []
        self.headings, self.links, self.images, self.metas, self.rel_links = [], [], [], [], []
        self.title, self.jsonld, self.addresses, self.times, self.quotes, self.buttons = [], [], [], [], [], []
        self.capture = []
        self.script = None
        self.inline = None
        self.script_srcs, self.inline_js = [], []
        self.style, self.css = None, []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = tag in {"script", "style", "noscript", "template", "head"} or "hidden" in attrs or attrs.get("aria-hidden") == "true" or bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", attrs.get("style", ""), re.I))
        void = tag in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
        if not void:
            self.stack.append((tag, hidden))
            self.hidden += int(hidden)
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.script = []
        elif tag == "script":
            if attrs.get("src"):
                self.script_srcs.append(attrs["src"])
            self.inline = []
        if tag == "style":
            self.style = []
        if attrs.get("style") and "font" in attrs["style"]:
            self.css.append(attrs["style"])
        if tag == "iframe" and attrs.get("src"):
            self.script_srcs.append(attrs["src"])
        if tag == "meta":
            self.metas.append(attrs)
        if tag == "link":
            self.rel_links.append(attrs)
        if tag == "img" and not self.hidden:
            self.images.append({"url": self.safe_url(attrs.get("src", "")), "alt": attrs.get("alt"), "title": attrs.get("title")})
        if tag in {"title", "h1", "h2", "h3", "h4", "h5", "h6", "a", "address", "time", "blockquote", "button"} and (not self.hidden or tag == "title"):
            self.capture.append({"tag": tag, "attrs": attrs, "parts": []})
        if tag in {"p", "div", "br", "li", "section"}:
            self.text.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def safe_url(self, value):
        try:
            return normalize(value, self.url) if value else None
        except ValueError:
            return None

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if self.style is not None and sum(map(len, self.css)) < 500_000:
            self.style.append(data)
        if self.inline is not None and sum(map(len, self.inline_js)) < 500_000:
            self.inline.append(data)
        if not self.hidden:
            self.text.append(data)
        for item in self.capture:
            if not self.hidden or item["tag"] == "title":
                item["parts"].append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.jsonld.append("".join(self.script))
            self.script = None
        elif tag == "style" and self.style is not None:
            self.css.append("".join(self.style))
            self.style = None
        elif tag == "script" and self.inline is not None:
            self.inline_js.append("".join(self.inline))
            self.inline = None
        for i in range(len(self.capture) - 1, -1, -1):
            item = self.capture[i]
            if item["tag"] != tag:
                continue
            self.capture.pop(i)
            text, attrs = clean("".join(item["parts"])), item["attrs"]
            if tag == "title":
                self.title.append(text)
            elif re.fullmatch(r"h[1-6]", tag):
                self.headings.append({"level": int(tag[1]), "text": text})
            elif tag == "a":
                href = attrs.get("href", "")
                url = self.safe_url(href)
                if url:
                    self.links.append({"url": url, "text": text, "rel": attrs.get("rel", "")})
                elif href.startswith(("tel:", "mailto:")):
                    self.links.append({"url": href, "text": text, "rel": ""})
            elif tag == "address":
                self.addresses.append(text)
            elif tag == "time":
                self.times.append({"text": text, "datetime": attrs.get("datetime")})
            elif tag == "blockquote":
                self.quotes.append({"text": text, "cite": attrs.get("cite"), "kind": "OBSERVED"})
            elif tag == "button":
                self.buttons.append(text)
            break
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self.hidden -= sum(int(hidden) for _, hidden in self.stack[i:])
                del self.stack[i:]
                break
        if tag in {"p", "div", "li", "section"} or re.fullmatch(r"h[1-6]", tag):
            self.text.append("\n")


def font_families(css):
    """Family names from font-family declarations (including @font-face); `font:` shorthand is not parsed."""
    # ponytail: resolves var(--x) defined in the same CSS source, one level deep; others stay as "var(--x)".
    variables = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;}{]+)", css))
    names = set()
    for value in re.findall(r"font-family\s*:\s*([^;}{]+)", css, re.I):
        value = re.sub(r"var\(\s*(--[\w-]+)[^)]*\)", lambda m: variables.get(m.group(1), m.group(0)), value)
        for name in value.split(","):
            name = name.replace("!important", "").strip().strip("'\"").strip()
            if name:
                names.add(name)
    return sorted(names)


def classify(url, title, headings):
    path = urlsplit(url).path.lower().strip("/")
    rules = [("about", r"about|our-story"), ("case-study", r"case-stud|success-stor"),
             ("testimonial", r"testimonial|reviews"), ("pricing", r"pricing|plans"),
             ("contact", r"contact"), ("careers", r"careers|jobs"), ("legal", r"privacy|terms|legal|cookies"),
             ("location", r"locations?|offices"), ("person", r"team|people|staff|author"),
             ("service", r"services?|solutions"), ("product", r"products?|shop"),
             ("article", r"blog|news|articles"), ("resource", r"resources?|guides|downloads")]
    if not path:
        return {"label": "homepage", "kind": "INFERRED", "confidence": 0.95, "evidence": ["URL path is /"]}
    for label, pattern in rules:
        if re.search(r"(?:^|/)(?:" + pattern + r")", path):
            return {"label": label, "kind": "INFERRED", "confidence": 0.75, "evidence": [f"URL path matches {pattern}: /{path}"]}
    return {"label": "other", "kind": "INFERRED", "confidence": 0.3, "evidence": ["No URL classification rule matched"]}


def extract(html: str, url: str) -> dict:
    p = Parser(url)
    p.feed(html)
    meta = {m.get("name", m.get("property", "")).lower(): m.get("content", "") for m in p.metas}
    canonical, feeds = None, []
    for link in p.rel_links:
        rel = link.get("rel", "").lower().split()
        if "canonical" in rel:
            canonical = p.safe_url(link.get("href", ""))
        if "alternate" in rel and link.get("type") in {"application/rss+xml", "application/atom+xml"}:
            feeds.append({"url": p.safe_url(link.get("href", "")), "type": link["type"]})
    text = "\n".join(filter(None, (clean(line) for line in "".join(p.text).splitlines())))
    schema = parse_jsonld(p.jsonld)
    schema["issues"] = validate(schema["documents"], text)
    faqs, testimonials, addresses = [], [], list(p.addresses)
    for obj in objects(schema["documents"]):
        types = obj.get("@type", [])
        types = types if isinstance(types, list) else [types]
        if "Question" in types:
            faqs.append({"question": obj.get("name"), "answer": obj.get("acceptedAnswer"), "source": "JSON-LD", "kind": "EXTRACTED"})
        if "Review" in types:
            testimonials.append({"text": obj.get("reviewBody"), "author": obj.get("author"), "source": "JSON-LD", "kind": "EXTRACTED"})
        if "PostalAddress" in types:
            addresses.append({k: v for k, v in obj.items() if k != "@context"})
    emails = sorted(set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text) + [l["url"][7:].split("?")[0] for l in p.links if l["url"].startswith("mailto:")]))
    phones = sorted(set(l["url"][4:] for l in p.links if l["url"].startswith("tel:")))
    ctas = [{"text": l["text"], "url": l["url"], "kind": "INFERRED", "confidence": 0.65} for l in p.links if re.search(r"\b(book|buy|schedule|contact|subscribe|sign up|get started|request|call|download)\b", l["text"], re.I)]
    ctas.extend({"text": t, "kind": "INFERRED", "confidence": 0.5} for t in p.buttons if t)
    title = " ".join(p.title)
    return {"extraction_status": "EXTRACTED", "accessibility": check_html(html), "title": title, "meta_description": meta.get("description"),
            "canonical_url": canonical, "headings": p.headings, "visible_text": text,
            "links": [l for l in p.links if l["url"].startswith(("https://", "http://"))],
            "images": p.images, "json_ld": schema, "open_graph": {k: v for k, v in meta.items() if k.startswith("og:")},
            "author": meta.get("author"), "dates": {k: v for k, v in meta.items() if k in {"article:published_time", "article:modified_time", "date", "datepublished", "datemodified"}},
            "times": p.times, "addresses": addresses, "telephone_numbers": phones, "emails": emails,
            "ctas": ctas, "faqs": faqs, "testimonials": testimonials, "quotation_candidates": p.quotes,
            "robots_meta": {k: v for k, v in meta.items() if k in {"robots", "googlebot", "bingbot"}},
            "social_meta": {k: v for k, v in meta.items() if k.startswith(("og:", "twitter:", "fb:"))},
            "icons": [{"rel": l.get("rel"), "href": p.safe_url(l.get("href", "")), "sizes": l.get("sizes")} for l in p.rel_links
                      if set(l.get("rel", "").lower().split()) & {"icon", "apple-touch-icon"}],
            "script_sources": sorted(set(filter(None, (p.safe_url(s) or s for s in p.script_srcs)))),
            "measurement": detect(p.script_srcs, "\n".join(p.inline_js)),
            "stylesheets": [u for l in p.rel_links if "stylesheet" in l.get("rel", "").lower().split() and (u := p.safe_url(l.get("href", "")))],
            "inline_font_families": font_families("\n".join(p.css)),
            "feeds": feeds, "classification": classify(url, title, p.headings),
            "limitations": ["HTML only; CSS, JavaScript and visual layout are not evaluated", "CTAs and page classes are heuristic inferences; unstructured FAQs/testimonials are not asserted"]}
