"""
Utilidades para normalización y filtrado geográfico inteligente.
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

_TARGET_ALIASES = {
    "dubai": {
        "dubai",
        "dubai healthcare city",
        "jumeirah",
        "dch",
        "business bay",
        "downtown dubai",
        "marina",
        "dubai marina",
        "jlt",
        "jumeirah lake towers",
        "uae",
        "united arab emirates",
    }
}

_STRONG_COUNTRY_REJECTIONS = {
    "germany",
    "india",
    "pakistan",
    "bangladesh",
    "nepal",
    "uk",
    "united kingdom",
    "ukraine",
    "russia",
    "france",
    "spain",
    "italy",
    "portugal",
    "turkey",
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
        "aliases": _TARGET_ALIASES.get(_norm(city), { _norm(city) }) | ({_norm(country)} if country else set()),
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


def _contains_any(haystack: str, needles: set[str]) -> str:
    for needle in sorted(needles, key=len, reverse=True):
        if needle and needle in haystack:
            return needle
    return ""


def geo_match_reason(item: dict, target: dict) -> tuple[bool, str]:
    geo = extract_geo_fields(item)
    city = _norm(geo["city"])
    country = _norm(geo["country"])
    address = _norm(geo["address"])
    formatted = _norm(geo["formatted_address"])
    combined = " | ".join(v for v in [city, country, address, formatted] if v)
    target_city = target["city_norm"]
    target_country = target["country_norm"]
    aliases = set(target.get("aliases") or set())
    aliases.add(target_city)
    if target_country:
        aliases.add(target_country)

    rejected_country = _contains_any(combined, _STRONG_COUNTRY_REJECTIONS - ({target_country} if target_country else set()))
    if rejected_country:
        return False, f"rejected_country:{rejected_country}"

    if target_country:
        if country == target_country or target_country in country:
            return True, "accepted_country_field"
        if target_country in address or target_country in formatted:
            return True, "accepted_country_address"

    if city and any(alias == city or alias in city or city in alias for alias in aliases):
        return True, "accepted_city_field"

    matched_alias = _contains_any(address, aliases) or _contains_any(formatted, aliases)
    if matched_alias:
        return True, f"accepted_alias:{matched_alias}"

    return False, "rejected_no_geo_match"


def location_matches_target(item: dict, target: dict) -> bool:
    return geo_match_reason(item, target)[0]
