"""Google Business Profile: is the business's Google listing consistent with its website, and what do its reviews show?

One Places API (New) Text Search for the business name and city. A result counts as this business only when its website
is this domain or its phone is one of the site's; otherwise nothing is picked, so a namesake is never reported as the
listing. The API key goes in a header and never enters the bundle."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import now
from . import identity

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ["id", "displayName", "formattedAddress", "addressComponents", "nationalPhoneNumber", "internationalPhoneNumber",
          "websiteUri", "googleMapsUri", "primaryType", "primaryTypeDisplayName", "types", "businessStatus",
          "regularOpeningHours", "rating", "userRatingCount", "reviews"]
DETAILED_WORDS = 20  # ponytail: a review this long usually describes an experience; a heuristic, not a quality score.
LIMITATION = ("One Google Places text search for the business name and city. Google returns at most 5 reviews, chosen "
              "by relevance, not the newest, so review dates and detail describe that sample only; the rating and count "
              "cover all reviews. Hours are recorded, not compared. Other listings (Apple, Bing, Yelp, directories) are "
              "not checked.")


def search(query, key, timeout):
    body = json.dumps({"textQuery": query, "pageSize": 5}).encode()
    request = Request(URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": ",".join(f"places.{f}" for f in FIELDS)})
    with urlopen(request, timeout=timeout) as r:
        return json.load(r).get("places") or []


def component(place, kind):
    return next((c.get("longText") for c in place.get("addressComponents") or []
                 if isinstance(c, dict) and kind in (c.get("types") or [])), None)


def squeeze(value):
    """Lowercase letters and digits only, so "N1H 1G5" matches "n1h1g5" and "Acme Dental, Inc." matches "acmedentalinc"."""
    return re.sub(r"[^a-z0-9]", "", value.lower()) if isinstance(value, str) else ""


def site_facts(pages):
    """Postal codes and street addresses the site states: JSON-LD PostalAddress first, then <address> text and page text."""
    structured, text = [], []
    for page in pages:
        for a in page.get("addresses") or []:
            if isinstance(a, dict):
                structured.append(a)
            elif isinstance(a, str):
                text.append(a)
        if isinstance(page.get("visible_text"), str):
            text.append(page["visible_text"])
    return structured, (" ".join(text) + " " + " ".join(str(v) for a in structured for v in a.values())).lower()


def match(place, domain, phones):
    """How a result is tied to this site: its website host, else its phone; None when neither."""
    if identity.host(place.get("websiteUri")) == domain:
        return "website"
    listed = {identity.digits(place.get(k)) for k in ("nationalPhoneNumber", "internationalPhoneNumber")} - {""}
    return "phone" if listed & set(phones) else None


def same_name(listed, names):
    """True when a site name equals the listing's (ignoring case and punctuation), "variant" when one contains the other."""
    if not (listed and names):
        return None
    if any(squeeze(listed) == squeeze(n) for n in names):
        return True
    return "variant" if any(squeeze(n) and (squeeze(n) in squeeze(listed) or squeeze(listed) in squeeze(n)) for n in names) else False


def compare(place, profile, domain, site_text):
    """One row per fact: what Google lists, what the site states, and whether they agree (None when either is missing)."""
    names = profile["names"]
    google_name = (place.get("displayName") or {}).get("text")
    phone = identity.digits(place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber"))
    postal, number = component(place, "postal_code"), component(place, "street_number")
    rows = [
        ("name", google_name, names[0] if names else None, same_name(google_name, names)),
        ("phone", place.get("nationalPhoneNumber"), ", ".join(profile["phones"]) or None,
         None if not (phone and profile["phones"]) else phone in profile["phones"]),
        ("website", place.get("websiteUri"), domain,
         None if not place.get("websiteUri") else identity.host(place["websiteUri"]) == domain),
        ("postal_code", postal, None, None if not postal else squeeze(postal) in squeeze(site_text)),
        ("street_number", number, None, None if not number else bool(re.search(rf"(?<![0-9]){re.escape(number)}(?![0-9])", site_text))),
        ("category", place.get("primaryTypeDisplayName", {}).get("text") or place.get("primaryType"),
         ", ".join(profile["categories"]) or None, None),
    ]
    return [{"field": f, "google": g, "site": s, "agrees": a} for f, g, s, a in rows]


def reviews(place):
    rows = []
    for r in place.get("reviews") or []:
        if isinstance(r, dict):
            body = ((r.get("text") or {}).get("text") or "").strip()
            # Reviewer names and photos are left out: the bundle keeps what the review says, not who wrote it.
            rows.append({"rating": r.get("rating"), "published": r.get("publishTime"), "relative": r.get("relativePublishTimeDescription"),
                         "words": len(body.split()), "text": body})
    dates = sorted(r["published"] for r in rows if isinstance(r["published"], str))
    return {"rating": place.get("rating"), "count": place.get("userRatingCount"), "sample": len(rows),
            "sample_latest": dates[-1] if dates else None, "sample_oldest": dates[0] if dates else None,
            "sample_detailed": sum(r["words"] >= DETAILED_WORDS for r in rows), "reviews": rows}


def collect(client, discovery, pages, brand):
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    config = getattr(client, "config", None)
    domain = identity.host(discovery["origin"])
    profile = identity.build(discovery["origin"], pages, None if identity.host(brand) == domain else brand, getattr(config, "location", None))
    name = profile["names"][0] if profile["names"] else brand
    query = " ".join(filter(None, [name, getattr(config, "location", None) or (profile["cities"][0] if profile["cities"] else None)]))
    base = {"query": query, "retrieved_at": now(), "kind": "OBSERVED", "limitation": LIMITATION}
    if not key:
        return {**base, "status": "UNKNOWN", "reason": "no_key", "note": "Set GOOGLE_PLACES_API_KEY to enable."}
    try:
        places = search(query, key, getattr(config, "timeout", 15))
    except HTTPError as exc:
        return {**base, "status": "UNKNOWN", "reason": "api_error", "error": exc.read(2000).decode("utf-8", "replace")}
    except (URLError, OSError, ValueError) as exc:
        return {**base, "status": "UNKNOWN", "reason": "request_failed", "error": str(exc)}
    candidates = [{"name": (p.get("displayName") or {}).get("text"), "address": p.get("formattedAddress"),
                   "website": p.get("websiteUri"), "maps": p.get("googleMapsUri"), "matched_by": match(p, domain, profile["phones"])}
                  for p in places if isinstance(p, dict)]
    place = next((p for p, c in zip(places, candidates) if c["matched_by"]), None)
    if place is None:  # No result ties to this site: not proof there's no listing, but none was found for this query.
        return {**base, "status": "OBSERVED", "found": False, "candidates": candidates}
    structured, site_text = site_facts(pages)
    checks = compare(place, profile, domain, site_text)
    # Summary first: the report digest trims each file from the end.
    return {**base, "status": "OBSERVED", "found": True, "matched_by": match(place, domain, profile["phones"]),
            "mismatches": [c["field"] for c in checks if c["agrees"] is False], "checks": checks,
            "reviews": reviews(place),
            "listing": {"name": (place.get("displayName") or {}).get("text"), "address": place.get("formattedAddress"),
                        "phone": place.get("nationalPhoneNumber"), "website": place.get("websiteUri"),
                        "maps": place.get("googleMapsUri"), "category": place.get("primaryType"), "types": place.get("types"),
                        "business_status": place.get("businessStatus"),
                        "hours": (place.get("regularOpeningHours") or {}).get("weekdayDescriptions")},
            "site_addresses": structured, "candidates": candidates}
