"""
mindgalaxy.places
=================

Nearby places *with ratings and reviews*, from Google's Places API (New).

OpenStreetMap (used in the browser) knows where places are but has no
ratings. When GOOGLE_MAPS_API_KEY is set, the server asks Google instead --
one Text Search per lookup, returning up to 20 places, each with its star
rating, number of ratings and up to five reviews (good and bad alike).

Cost control: Google includes a free monthly allowance per API. Every call is
counted, per user per day and for the whole site per month, and the server
stops asking Google (falling back to OpenStreetMap) before the site's monthly
cap -- GOOGLE_PLACES_MONTHLY_CAP, 900 by default -- is reached. Results are
kept in memory for 10 minutes only; Google's terms don't allow storing them.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location", "places.rating",
    "places.userRatingCount", "places.googleMapsUri", "places.currentOpeningHours.openNow",
    "places.nationalPhoneNumber", "places.websiteUri", "places.primaryTypeDisplayName", "places.reviews",
    "places.businessStatus",
])
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
CACHE_SECONDS = 600


class PlacesError(Exception):
    pass


def _km(a: float, b: float, c: float, d: float) -> float:
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def _review(r: dict[str, Any]) -> dict[str, Any]:
    author = r.get("authorAttribution") or {}
    text = (r.get("text") or r.get("originalText") or {}).get("text", "")
    return {
        "rating": r.get("rating"),
        "text": text[:600],
        "when": r.get("relativePublishTimeDescription", ""),
        "author": author.get("displayName", "A Google user"),
        "author_url": author.get("uri", ""),
    }


def normalise(raw: dict[str, Any], lat: float, lon: float) -> list[dict[str, Any]]:
    out = []
    for p in raw.get("places", []):
        if p.get("businessStatus") in ("CLOSED_PERMANENTLY",):
            continue
        loc = p.get("location") or {}
        plat, plon = loc.get("latitude"), loc.get("longitude")
        if plat is None or plon is None:
            continue
        reviews = [_review(r) for r in (p.get("reviews") or [])]
        out.append({
            "name": (p.get("displayName") or {}).get("text", "Unnamed place"),
            "type": (p.get("primaryTypeDisplayName") or {}).get("text", ""),
            "rating": p.get("rating"),
            "count": p.get("userRatingCount", 0),
            "address": p.get("formattedAddress", ""),
            "lat": plat, "lon": plon,
            "km": round(_km(lat, lon, plat, plon), 2),
            "maps_url": p.get("googleMapsUri", ""),
            "open_now": (p.get("currentOpeningHours") or {}).get("openNow"),
            "phone": p.get("nationalPhoneNumber", ""),
            "website": p.get("websiteUri", ""),
            "reviews": reviews,
        })
    return out


def search(key: str, query: str, lat: float, lon: float, radius_m: int = 10000,
           fetch: Optional[Callable[[urllib.request.Request], Any]] = None) -> list[dict[str, Any]]:
    """One Text Search near (lat, lon). Raises PlacesError on failure."""
    ck = f"{query.lower()}|{lat:.3f}|{lon:.3f}"
    hit = _cache.get(ck)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    body = {"textQuery": query, "pageSize": 20, "rankPreference": "RELEVANCE",
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radius_m)}}}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS})
    try:
        if fetch:
            raw = fetch(req)
        else:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # Google's own message (never includes the key)
        try:
            msg = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise PlacesError(f"Google Places error {e.code}: {msg[:200]}") from None
    except Exception as e:
        raise PlacesError(f"Google Places unreachable: {type(e).__name__}") from None
    places = normalise(raw, lat, lon)
    _cache[ck] = (time.time(), places)
    if len(_cache) > 500:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:250]:
            _cache.pop(k, None)
    return places
