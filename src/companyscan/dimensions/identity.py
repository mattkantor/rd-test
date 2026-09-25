"""Who the company is, and whether an LLM answer describes it or a namesake.

build() turns the crawl (JSON-LD, tel: links, linked social profiles, and an LLM read of the page text) plus what the
user supplied into a profile.
check() compares the facts an answer states against it. Plain Python: the LLM extracts facts, it never judges the match."""
import re
from urllib.parse import urlsplit

from ..scan.schema import entities, objects
from ..scan.social import discover_profiles

ORG_TYPES = {"Organization", "Corporation", "LocalBusiness", "ProfessionalService", "Store", "MedicalBusiness", "Dentist"}
GENERIC_TYPES = {"Organization", "Corporation", "LocalBusiness", "Thing", "Place"}


def add(items, value):
    """Append a stripped string unless blank or already present (case-insensitive)."""
    if isinstance(value, str) and value.strip() and value.strip().lower() not in {i.lower() for i in items}:
        items.append(value.strip())


def digits(phone):
    """Last 10 digits, so +1 (512) 555-0100 and 512.555.0100 compare equal; '' if too short to be a phone."""
    d = re.sub(r"\D", "", phone) if isinstance(phone, str) else ""
    return d[-10:] if len(d) >= 7 else ""


def host(url):
    try:
        h = urlsplit(url if "//" in url else f"//{url}").hostname if isinstance(url, str) and url.strip() else None
    except ValueError:
        h = None
    return (h or "").removeprefix("www.")


def as_list(value):
    return value if isinstance(value, list) else [value]


def is_org(obj):
    """A JSON-LD business: an organization type, or anything with a name and an address (Dentist, Restaurant, ...)."""
    types = {t for t in as_list(obj.get("@type")) if isinstance(t, str)}
    return bool(types & ORG_TYPES) or (bool(types) and "name" in obj and "address" in obj)


def build(domain, pages=(), company_name=None, location=None, site=None):
    """Identity profile: names, cities, phones, categories and official profiles. User-supplied values come first, then
    JSON-LD, then site (the LLM's read of the page text: reputation.read_site's identity), which fills gaps on sites
    without structured data."""
    profile = {"domain": host(domain), "names": [], "cities": [], "phones": [], "categories": [], "profiles": []}
    add(profile["names"], company_name)
    if isinstance(location, str):
        add(profile["cities"], location.split(",")[0])  # "Austin, TX, USA" -> Austin.
    for page in pages:
        for obj in entities(page.get("json_ld", {}).get("documents", [])):
            if not is_org(obj):
                continue
            for part in objects(obj.get("address")):
                add(profile["cities"], part.get("addressLocality"))
            for key in ("name", "alternateName", "legalName"):
                for name in as_list(obj.get(key)):
                    add(profile["names"], name)
            for phone in as_list(obj.get("telephone")):
                add(profile["phones"], digits(phone))
            for kind in as_list(obj.get("@type")):
                if isinstance(kind, str) and kind not in GENERIC_TYPES:
                    add(profile["categories"], re.sub(r"(?<=[a-z])(?=[A-Z])", " ", kind))  # LegalService -> Legal Service.
        for phone in page.get("telephone_numbers", []):
            add(profile["phones"], digits(phone))
    site = site if isinstance(site, dict) else {}
    for key, field in (("names", "company_name"), ("names", "other_names"), ("cities", "cities"),
                       ("phones", "phones"), ("categories", "category")):
        for value in as_list(site.get(field)):
            add(profile[key], digits(value) if key == "phones" else value)
    profile["profiles"] = [p["url"] for p in discover_profiles(pages) if p["official_confidence"] >= 0.75]
    return profile


def same_city(city, cities):
    """True/False when both sides name a city, None when either doesn't (a vague "Texas" is not a conflict)."""
    if not (isinstance(city, str) and city.strip() and cities):
        return None
    return any(re.search(rf"(?<![a-z]){re.escape(c.lower())}(?![a-z])", city.lower()) for c in cities)


def check(profile, stated, given=()):
    """Compare facts an answer states (website, city, phone, category) with the profile.
    given: facts that were in the prompt, so agreeing on them proves nothing (the model may just repeat them).
    Verdict: mismatch (any conflict: likely a namesake), confirmed (an independent fact agrees), else unconfirmed."""
    results = {}
    site = host(stated.get("website"))
    if site:
        owned = {profile["domain"], *map(host, profile["profiles"])}
        results["website"] = site in owned or site.endswith("." + profile["domain"])
    results["city"] = same_city(stated.get("city"), profile["cities"])
    phone = digits(stated.get("phone"))
    if phone and profile["phones"]:
        results["phone"] = phone in profile["phones"]
    category = stated.get("category")
    if isinstance(category, str) and any(c.lower() in category.lower() for c in profile["categories"]):
        results["category"] = True  # Agreement only: category wording varies too much to call a conflict.
    agree = [fact for fact, ok in results.items() if ok]
    conflict = [fact for fact, ok in results.items() if ok is False]
    independent = [fact for fact in agree if fact not in given]
    return {"verdict": "mismatch" if conflict else "confirmed" if independent else "unconfirmed",
            "agree": independent, "echoed": [fact for fact in agree if fact in given], "conflict": conflict}
