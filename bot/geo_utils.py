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
    },
    "valencia": {
        "valencia",
        "ciutat vella",
        "eixample",
        "campanar",
        "benimaclet",
        "ruzafa",
        "russafa",
        "el carmen",
        "patraix",
        "mestalla",
        "poblats maritims",
        "poblats marítims",
    },
    "buenos aires": {
        "buenos aires",
        "palermo",
        "recoleta",
        "belgrano",
        "caballito",
        "microcentro",
        "nunez",
        "nuñez",
        "san telmo",
        "barracas",
        "villa crespo",
        "puerto madero",
    },
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

_LOCATION_PRIORITY = (
    ("coordinates", 40),
    ("formatted_address", 26),
    ("locality", 22),
    ("administrative_area", 16),
    ("city", 12),
    ("neighborhood", 10),
    ("address", 6),
)


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
        "locality": (item.get("locality") or item.get("city") or item.get("town") or "").strip(),
        "administrative_area": (item.get("administrativeArea") or item.get("administrative_area") or item.get("state") or item.get("region") or "").strip(),
        "neighborhood": (item.get("neighborhood") or item.get("suburb") or item.get("district") or "").strip(),
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
    locality = _norm(geo["locality"])
    admin = _norm(geo["administrative_area"])
    neighborhood = _norm(geo["neighborhood"])
    country = _norm(geo["country"])
    address = _norm(geo["address"])
    formatted = _norm(geo["formatted_address"])
    coords = geo["lat"] is not None and geo["lng"] is not None
    target_city = target["city_norm"]
    target_country = target["country_norm"]
    aliases = set(target.get("aliases") or set())
    aliases.add(target_city)
    if target_country:
        aliases.add(target_country)

    matched_terms = []
    score = 0

    rejected_country = _contains_any(" | ".join(v for v in [country, address, formatted, admin] if v), _STRONG_COUNTRY_REJECTIONS - ({target_country} if target_country else set()))
    if rejected_country:
        return False, f"rejection_reason:strong_country:{rejected_country}|geo_score:0|matched_terms:[]"

    if coords:
        score += 40
        matched_terms.append("coordinates")

    for field_name, field_score in _LOCATION_PRIORITY:
        if field_name == "coordinates" or not field_score:
            continue
        if field_name == "formatted_address" and formatted:
            if target_city and target_city in formatted:
                score += field_score
                matched_terms.append("formatted_address")
        elif field_name == "locality" and locality:
            if locality in aliases or any(alias in locality or locality in alias for alias in aliases):
                score += field_score
                matched_terms.append("locality")
        elif field_name == "administrative_area" and admin:
            if admin in aliases or any(alias in admin or admin in alias for alias in aliases):
                score += field_score
                matched_terms.append("administrative_area")
        elif field_name == "city" and city:
            if city in aliases or any(alias in city or city in alias for alias in aliases):
                score += field_score
                matched_terms.append("city_field")
        elif field_name == "neighborhood" and neighborhood:
            if neighborhood in aliases or any(alias in neighborhood or neighborhood in alias for alias in aliases):
                score += field_score
                matched_terms.append("neighborhood")
        elif field_name == "address" and address:
            if _contains_any(address, aliases):
                score += field_score
                matched_terms.append("address")

    if target_country:
        if country == target_country or target_country in country:
            score += 24
            matched_terms.append("country_field")
        elif target_country in address or target_country in formatted or target_country in admin:
            score += 16
            matched_terms.append("country_context")

    if target_country and target_country in formatted:
        score += 8
        matched_terms.append("formatted_country")

    if target_country and target_country in address:
        score += 5
        matched_terms.append("address_country")

    if not matched_terms:
        return False, "rejection_reason:no_geo_signal|geo_score:0|matched_terms:[]"

    if score >= 20:
        return True, f"geo_score:{score}|matched_terms:{matched_terms}"

    return False, f"rejection_reason:low_score|geo_score:{score}|matched_terms:{matched_terms}"


def location_matches_target(item: dict, target: dict) -> bool:
    return geo_match_reason(item, target)[0]
