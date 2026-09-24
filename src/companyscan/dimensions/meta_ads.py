"""Meta Ad Library API keyword search for the brand. The access token never enters the bundle."""
import json
import os
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from ..models import now


def collect(client, discovery, pages, brand):
    token = os.environ.get("META_ACCESS_TOKEN")
    countries = os.environ.get("META_AD_COUNTRIES", "US").split(",")
    base = {"search_terms": brand, "countries": countries, "retrieved_at": now(),
            "limitation": "Meta's Ad Library API returns all ad types only for EU/UK delivery; elsewhere only political/issue ads. A keyword search can match other advertisers."}
    if not token:
        return {**base, "status": "UNKNOWN", "reason": "no_token", "note": "Set META_ACCESS_TOKEN to enable."}
    query = urlencode({"search_terms": brand, "ad_reached_countries": json.dumps(countries), "ad_type": "ALL",
                       "ad_active_status": "ALL", "limit": 50, "access_token": token,
                       "fields": "id,page_id,page_name,ad_creative_bodies,ad_creative_link_titles,ad_delivery_start_time,ad_delivery_stop_time,ad_snapshot_url,publisher_platforms"})
    # Unversioned Graph URL uses the app's default version. Not via Client: the token must never enter the bundle.
    try:
        with urlopen("https://graph.facebook.com/ads_archive?" + query, timeout=client.config.timeout) as r:
            data = json.load(r)
    except HTTPError as exc:
        return {**base, "status": "UNKNOWN", "reason": "api_error", "error": exc.read(2000).decode("utf-8", "replace")}
    except (URLError, OSError, ValueError) as exc:
        return {**base, "status": "UNKNOWN", "reason": "request_failed", "error": str(exc)}
    ads = data.get("data", [])
    return {**base, "status": "OBSERVED", "ad_count": len(ads), "more_available": bool(data.get("paging", {}).get("next")),
            "pages": dict(Counter(a.get("page_name") for a in ads)), "ads": ads}
