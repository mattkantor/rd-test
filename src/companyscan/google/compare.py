"""Pure comparison of a Business Profile location with a site profile. No network, no database."""
import re
from urllib.parse import urlsplit

# Fields the app may propose to change, by Google field-mask path.
EDITABLE = {
    "title": "Name",
    "phoneNumbers.primaryPhone": "Phone",
    "websiteUri": "Website",
    "profile.description": "Description",
}


def digits(text):
    return re.sub(r"\D", "", text or "")[-10:]  # Compare the last ten digits: ignores country code and punctuation.


def host(url):
    netloc = urlsplit(url if "//" in (url or "") else "//" + (url or "")).netloc.lower()
    return netloc.removeprefix("www.")


def current(location):
    """The editable fields as Google has them."""
    return {"title": location.get("title") or "", "phoneNumbers.primaryPhone": (location.get("phoneNumbers") or {}).get("primaryPhone") or "",
            "websiteUri": location.get("websiteUri") or "", "profile.description": (location.get("profile") or {}).get("description") or ""}


def wanted(profile):
    """What the site profile says each editable field should be; "" for a field the profile doesn't cover."""
    return {"title": profile.get("business_name") or "", "phoneNumbers.primaryPhone": profile.get("phone") or "",
            "websiteUri": profile.get("website") or "", "profile.description": profile.get("offering") or ""}


def same(field, a, b):
    if field == "phoneNumbers.primaryPhone":
        return digits(a) == digits(b)
    if field == "websiteUri":
        return host(a) == host(b)
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def mismatches(location, profile):
    """[{"field", "label", "current", "proposed"}] for each editable field the profile states and Google differs on."""
    have, want = current(location), wanted(profile)
    return [{"field": f, "label": label, "current": have[f], "proposed": want[f]}
            for f, label in EDITABLE.items() if want[f].strip() and not same(f, have[f], want[f])]


def matches_site(location, profile):
    """True when the location's website host or phone is the site's (the picker warns when neither is)."""
    return bool((host(location.get("websiteUri")) and host(location.get("websiteUri")) == host(profile.get("website")))
                or (digits((location.get("phoneNumbers") or {}).get("primaryPhone")) and
                    digits((location.get("phoneNumbers") or {}).get("primaryPhone")) == digits(profile.get("phone"))))
