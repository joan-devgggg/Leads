"""
Utilidades para normalización y filtrado geográfico estricto.
"""
import re
import unicodedata


_COUNTRY_ALIASES = {
    "spain": "spain",
    "españa": "spain",
    "espana": "spain",
    "uae": "united arab emirates",
    "united arab emirates": "united arab emirates",
    "dubai": "united arab emirates",
    "abu dhabi": "united arab emirates",
    "france": "france",
    "paris": "france",
    "argentina": "argentina",
    "buenos aires": "argentina",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def parse_target_location(zone: str) -> dict:
    raw = (zone or "").strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    city = parts[0] if parts else raw
    country = parts[1] if len(parts) > 1 else ""
    if not country:
        country = _COUNTRY_ALIASES.get(_norm(raw), "")
    if not country and city:
        country = _COUNTRY_ALIASES.get(_norm(city), "")
    return {
        "raw": raw,
        "city": city,
        "country": country,
        "city_norm": _norm(city),
        "country_norm": _norm(country),
        "raw_norm": _norm(raw),
    }


def extract_geo_fields(item: dict) -> dict:
    coords = item.get("coordinates") or item.get("location") or {}
    if isinstance(coords, dict):
        lat = coords.get("lat") or coords.get("latitude")
        lng = coords.get("lng") or coords.get("lon") or coords.get("longitude")
    else:
        lat = lng = None

    return {
        "address": (item.get("address") or "").strip(),
        "formatted_address": (item.get("formattedAddress") or item.get("formatted_address") or "").strip(),
        "city": (item.get("city") or item.get("locality") or item.get("neighborhood") or "").strip(),
        "country": (item.get("country") or item.get("countryName") or item.get("country_code") or item.get("countryCode") or "").strip(),
        "lat": lat,
        "lng": lng,
    }


def location_matches_target(item: dict, target: dict) -> bool:
    geo = extract_geo_fields(item)
    city = _norm(geo["city"])
    country = _norm(geo["country"])
    address = _norm(geo["address"])
    formatted = _norm(geo["formatted_address"])
    target_city = target["city_norm"]
    target_country = target["country_norm"]

    city_ok = bool(target_city) and (
        city == target_city or
        target_city in city or
        target_city in address or
        target_city in formatted
    )
    if not city_ok:
        return False

    if target_country:
        return (
            country == target_country or
            target_country in address or
            target_country in formatted
        )
    return True
