"""
Utilidades para resolución y expansión geográfica global.
"""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests

from state_store import cache_get, cache_set, acquire

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).with_name("geo_cache.json")
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_HEADERS = {"User-Agent": "LeadsBot/1.0 (geo resolver)"}


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
    "london": {
        "london",
        "city of london",
        "westminster",
        "kensington",
        "chelsea",
        "canary wharf",
        "soho",
        "shoreditch",
        "camden",
    },
    "new york": {
        "new york",
        "nyc",
        "manhattan",
        "brooklyn",
        "queens",
        "bronx",
        "staten island",
        "midtown",
        "upper east side",
        "upper west side",
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

_CITY_THRESHOLDS = {
    "dubai": 18,
    "london": 18,
    "new york": 18,
    "valencia": 26,
    "buenos aires": 22,
}

_REGIONAL_THRESHOLDS = {
    "mega_city": 18,
    "large_city": 20,
    "medium_city": 24,
    "small_city": 28,
}

_CITY_CLASS_ALIASES = {
    "mega_city": {"dubai", "london", "new york", "new york city", "nyc"},
    "large_city": {"valencia", "milan", "lisbon", "buenos aires"},
    "medium_city": set(),
    "small_city": set(),
}

_TYPE_PRIORITY = {
    "country": 5,
    "region": 4,
    "state": 4,
    "province": 4,
    "metro_area": 3,
    "mega_city": 3,
    "medium_city": 2,
    "small_city": 1,
}


@dataclass(frozen=True)
class SearchPoint:
    name: str
    latitude: float
    longitude: float
    radius: int


def _load_cache() -> dict:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=True, indent=2, sort_keys=True))
    except Exception:
        logger.exception("No se pudo guardar cache geográfica")


def _cache_get(key: str):
    value = cache_get(key)
    if value is not None:
        logger.info("[CACHE] cache_hit=true key=%s", key)
        return value
    return _load_cache().get(key)


def _cache_set(key: str, value: dict) -> None:
    cache_set(key, value)
    cache = _load_cache()
    cache[key] = value
    _save_cache(cache)


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
    city_type = classify_city_type(city)
    return {
        "raw": raw,
        "city": city,
        "country": country,
        "city_norm": _norm(city),
        "country_norm": _norm(country),
        "raw_norm": _norm(raw),
        "aliases": _TARGET_ALIASES.get(_norm(city), { _norm(city) }) | ({_norm(country)} if country else set()),
        "city_type": city_type,
        "threshold": _CITY_THRESHOLDS.get(_norm(city), _REGIONAL_THRESHOLDS[city_type]),
    }


def classify_city_type(city: str) -> str:
    city_norm = _norm(city)
    for city_type, aliases in _CITY_CLASS_ALIASES.items():
        if city_norm in aliases:
            return city_type
    if any(token in city_norm for token in ("district", "county", "province", "prefecture")):
        return "small_city"
    if any(token in city_norm for token in ("metropolitan", "metro", "city")):
        return "medium_city"
    return "medium_city"


def classify_zone_kind(name: str, osm_class: str = "", osm_type: str = "") -> str:
    n = _norm(name)
    c = _norm(osm_class)
    t = _norm(osm_type)
    if c == "boundary" and t == "administrative":
        if any(x in n for x in ("spain", "argentina", "france", "italy", "portugal", "united states")):
            return "country"
        if any(x in n for x in ("state", "province", "region", "autonomous", "community", "county")):
            return "region"
        return "province"
    if c in {"place", "boundary"}:
        if any(x in n for x in ("metro", "metropolitan")):
            return "metro_area"
        if any(x in n for x in ("city", "town", "municipality")):
            return "medium_city"
        return "small_city"
    return "small_city"


def _bbox_center(bounds: list[float]) -> tuple[float, float]:
    south, north, west, east = bounds
    return ((float(south) + float(north)) / 2.0, (float(west) + float(east)) / 2.0)


def _bbox_to_grid(bounds: list[float], density: int, *, max_points: int = 16) -> list[SearchPoint]:
    south, north, west, east = [float(x) for x in bounds]
    rows = cols = max(1, density)
    lat_step = (north - south) / rows
    lng_step = (east - west) / cols
    points = []
    for r in range(rows):
        for c in range(cols):
            lat = south + (r + 0.5) * lat_step
            lng = west + (c + 0.5) * lng_step
            radius = int(max(1500, min(12000, 2200 + max(north - south, east - west) * 110000)))
            points.append(SearchPoint(f"grid_{r+1}_{c+1}", round(lat, 6), round(lng, 6), radius))
            if len(points) >= max_points:
                return points
    return points


def _dedupe_points(points: list[SearchPoint]) -> list[SearchPoint]:
    seen = set()
    out = []
    for point in points:
        key = (round(point.latitude, 4), round(point.longitude, 4), point.radius)
        if key in seen:
            continue
        seen.add(key)
        out.append(point)
    return out


def resolve_geo_target(zone: str) -> dict:
    raw = (zone or "").strip()
    cached = _cache_get(f"resolve::{_norm(raw)}")
    if cached:
        return cached

    params = {
        "q": raw,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
    }
    acquire("nominatim", 1.1)
    response = requests.get(_NOMINATIM_URL, params=params, headers=_HEADERS, timeout=20)
    response.raise_for_status()
    items = response.json() if response.text.strip() else []
    if not items:
        target = parse_target_location(raw)
        target.update({"display_name": raw, "kind": "small_city", "bounds": [], "center": None, "coordinates": []})
        return target

    item = items[0]
    address = item.get("address") or {}
    kind = classify_zone_kind(item.get("display_name") or raw, item.get("class") or "", item.get("type") or "")
    bbox = [float(v) for v in (item.get("boundingbox") or [])]
    center = (float(item.get("lat")), float(item.get("lon"))) if item.get("lat") and item.get("lon") else None
    target = parse_target_location(raw)
    target.update({
        "display_name": item.get("display_name") or raw,
        "kind": kind,
        "osm_class": item.get("class") or "",
        "osm_type": item.get("type") or "",
        "bounds": bbox,
        "center": center,
        "address": address,
    })
    _cache_set(f"resolve::{_norm(raw)}", target)
    return target


def _nearby_subzones(target: dict, count_hint: int, *, max_points: int = 10) -> list[dict]:
    bounds = target.get("bounds") or []
    if len(bounds) != 4:
        return []
    south, north, west, east = [float(v) for v in bounds]
    viewbox = f"{west},{north},{east},{south}"
    params = {
        "format": "jsonv2",
        "addressdetails": 1,
        "q": target.get("raw", ""),
        "bounded": 1,
        "viewbox": viewbox,
        "limit": max(5, min(max_points, max(10, min(40, count_hint // 10 + 10)))),
    }
    try:
        acquire("nominatim", 1.1)
        response = requests.get(_NOMINATIM_URL, params=params, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        items = response.json() if response.text.strip() else []
    except Exception:
        return []

    subzones = []
    for item in items[:max_points]:
        name = item.get("display_name", "")
        if not name:
            continue
        subzones.append({
            "name": name.split(",")[0],
            "latitude": float(item.get("lat", 0.0)),
            "longitude": float(item.get("lon", 0.0)),
            "radius": 3500,
            "kind": classify_zone_kind(name, item.get("class") or "", item.get("type") or ""),
        })
    return subzones


def build_geo_plan(zone: str, requested_count: int) -> dict:
    target = resolve_geo_target(zone)
    kind = target.get("kind") or "small_city"
    center = target.get("center")
    bounds = target.get("bounds") or []

    points: list[SearchPoint] = []
    if center:
        lat, lng = center
        base_radius = 2500 if kind in {"small_city", "medium_city"} else 4000
        points.append(SearchPoint(target.get("display_name", target["raw"]), lat, lng, base_radius))

    if len(bounds) == 4:
        size = max(bounds[1] - bounds[0], bounds[3] - bounds[2])
        if kind == "country" or requested_count >= 500:
            density = 4 if size > 10 else 3
        elif kind in {"region", "state", "province"} or requested_count >= 100:
            density = 3 if size > 2 else 2
        elif kind in {"metro_area", "mega_city"}:
            density = 3
        else:
            density = 2
        points.extend(_bbox_to_grid(bounds, density, max_points=16 if requested_count < 500 else 25))

    if kind in {"medium_city", "mega_city", "metro_area"}:
        points.extend(_nearby_subzones(target, requested_count, max_points=12 if requested_count < 500 else 20))

    points = _dedupe_points(points)
    if requested_count >= 5000 and len(points) < 25 and len(bounds) == 4:
        points.extend(_bbox_to_grid(bounds, 5, max_points=25))
        points = _dedupe_points(points)

    cache_value = {"target": target, "points": [point.__dict__ for point in points]}
    _cache_set(f"plan::{_norm(zone)}::{requested_count}", cache_value)
    return cache_value


def extract_geo_fields(item: dict) -> dict:
    coords = item.get("coordinates") or item.get("location") or item.get("geometry") or {}
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
        "has_geometry": bool(item.get("geometry") or item.get("location")),
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
    has_geometry = bool(geo.get("has_geometry"))
    target_city = target["city_norm"]
    target_country = target["country_norm"]
    city_type = target.get("city_type") or classify_city_type(target.get("city", ""))
    threshold = int(target.get("threshold") or _REGIONAL_THRESHOLDS["medium"])
    aliases = set(target.get("aliases") or set())
    aliases.add(target_city)
    if target_country:
        aliases.add(target_country)

    matched_terms = []
    score = 0
    confidence = 0.0

    rejected_country = _contains_any(" | ".join(v for v in [country, address, formatted, admin] if v), _STRONG_COUNTRY_REJECTIONS - ({target_country} if target_country else set()))
    if rejected_country:
        return False, f"rejection_reason:strong_country:{rejected_country}|geo_score:0|matched_terms:[]"

    if coords:
        score += 40
        matched_terms.append("coordinates")
        confidence += 0.35
    if has_geometry:
        score += 12
        matched_terms.append("geometry")
        confidence += 0.1

    for field_name, field_score in _LOCATION_PRIORITY:
        if field_name == "coordinates" or not field_score:
            continue
        if field_name == "formatted_address" and formatted:
            if target_city and target_city in formatted:
                score += field_score
                matched_terms.append("formatted_address")
                confidence += 0.08
        elif field_name == "locality" and locality:
            if locality in aliases or any(alias in locality or locality in alias for alias in aliases):
                score += field_score
                matched_terms.append("locality")
                confidence += 0.14
        elif field_name == "administrative_area" and admin:
            if admin in aliases or any(alias in admin or admin in alias for alias in aliases):
                score += field_score
                matched_terms.append("administrative_area")
                confidence += 0.12
        elif field_name == "city" and city:
            if city in aliases or any(alias in city or city in alias for alias in aliases):
                score += field_score
                matched_terms.append("city_field")
                confidence += 0.1
        elif field_name == "neighborhood" and neighborhood:
            if neighborhood in aliases or any(alias in neighborhood or neighborhood in alias for alias in aliases):
                score += field_score
                matched_terms.append("neighborhood")
                confidence += 0.08
        elif field_name == "address" and address:
            if _contains_any(address, aliases):
                score += field_score
                matched_terms.append("address")
                confidence += 0.05

    if target_country:
        if country == target_country or target_country in country:
            score += 24
            matched_terms.append("country_field")
            confidence += 0.15
        elif target_country in address or target_country in formatted or target_country in admin:
            score += 16
            matched_terms.append("country_context")
            confidence += 0.1

    if target_country and target_country in formatted:
        score += 8
        matched_terms.append("formatted_country")
        confidence += 0.06

    if target_country and target_country in address:
        score += 5
        matched_terms.append("address_country")
        confidence += 0.04

    if city_type == "mega_city" and coords:
        threshold = max(16, threshold - 2)
    elif city_type == "large_city" and (coords or has_geometry):
        threshold = max(18, threshold - 1)

    if coords and not formatted:
        threshold -= 2
    if coords and not target_country:
        threshold -= 1

    confidence = min(confidence, 0.99)

    if not matched_terms:
        return False, f"rejection_reason:no_geo_signal|city_type:{city_type}|threshold:{threshold}|geo_score:0|confidence:0.0|matched_geo_fields:[]"

    if score >= threshold:
        return True, f"accepted|city_type:{city_type}|threshold:{threshold}|geo_score:{score}|confidence:{round(confidence, 2)}|matched_geo_fields:{matched_terms}"

    return False, f"rejected|city_type:{city_type}|threshold:{threshold}|rejection_reason:low_score|geo_score:{score}|confidence:{round(confidence, 2)}|matched_geo_fields:{matched_terms}"


def location_matches_target(item: dict, target: dict) -> bool:
    return geo_match_reason(item, target)[0]


def plan_to_points(plan: dict) -> list[SearchPoint]:
    return [SearchPoint(**point) for point in plan.get("points", [])]
