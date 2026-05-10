"""
Wrapper de Apify Google Maps Scraper, generalizado desde scrape_clinicas_dubai.py.
"""
import logging
import time
import unicodedata
import re
from dataclasses import dataclass
from itertools import product

import requests
from config import APIFY_API_TOKEN, APIFY_ACTOR_ID, APIFY_TIMEOUT_SECS, HTTP_TIMEOUT_SECS
from json_utils import make_json_safe
from geo_utils import build_geo_plan, extract_geo_fields, geo_match_reason, plan_to_points, resolve_geo_target
from planner import build_adaptive_plan
from keyword_profiles import country_keywords, country_languages, language_keywords
from state_store import get_keyword_stats, update_keyword_stats
from search_budget import SearchBudget

BASE_URL = "https://api.apify.com/v2"
HEADERS  = {"Authorization": f"Bearer {APIFY_API_TOKEN}"}

logger = logging.getLogger(__name__)

SEARCH_KEYWORDS = ["aesthetic clinic", "beauty clinic", "cosmetic clinic", "dermatology clinic", "laser clinic", "plastic surgery clinic", "skin clinic", "medical spa"]


@dataclass(frozen=True)
class SearchPoint:
    name: str
    latitude: float
    longitude: float
    radius: int


def _log_response(label: str, response: requests.Response) -> None:
    logger.info(
        "%s | url=%s | status=%s | content_type=%s | body=%r",
        label,
        response.url,
        response.status_code,
        response.headers.get("content-type"),
        response.text[:1000],
    )


def _safe_json(response: requests.Response, label: str):
    _log_response(label, response)

    body = response.text.strip()
    if not body:
        raise RuntimeError(f"Apify devolvió una respuesta vacía en {label} ({response.url})")

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Apify devolvió JSON inválido en {label} ({response.url}): {body[:500]}"
        ) from exc


def _run_actor(run_input: dict) -> list[dict]:
    run_url = f"{BASE_URL}/acts/{APIFY_ACTOR_ID}/runs"
    logger.info("Apify POST %s", run_url)
    r = requests.post(
        run_url,
        headers=HEADERS,
        json=make_json_safe(run_input),
        params={"timeout": APIFY_TIMEOUT_SECS},
        timeout=HTTP_TIMEOUT_SECS,
    )
    _log_response("Apify create run", r)
    r.raise_for_status()

    payload = _safe_json(r, "Apify create run")
    run_id = payload.get("data", {}).get("id")
    if not run_id:
        raise RuntimeError(f"Apify no devolvió run_id en {run_url}: {payload}")

    deadline = time.time() + APIFY_TIMEOUT_SECS
    while time.time() < deadline:
        status_url = f"{BASE_URL}/actor-runs/{run_id}"
        logger.info("Apify GET %s", status_url)
        s_resp = requests.get(status_url, headers=HEADERS, timeout=HTTP_TIMEOUT_SECS)
        _log_response("Apify run status", s_resp)
        s_resp.raise_for_status()
        s_payload = _safe_json(s_resp, "Apify run status")
        s = s_payload.get("data") or {}
        status = s.get("status")
        if not status:
            raise RuntimeError(f"Apify no devolvió status en {status_url}: {s_payload}")
        logger.info("Apify run status=%s run_id=%s", status, run_id)
        if status == "SUCCEEDED":
            dataset_id = s.get("defaultDatasetId")
            if not dataset_id:
                raise RuntimeError(f"Apify no devolvió defaultDatasetId en {status_url}: {s_payload}")
            return _fetch_dataset_items(dataset_id)
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify terminó con estado: {status}")
        time.sleep(5)
    raise TimeoutError("El actor de Apify no terminó a tiempo.")


def _fetch_dataset_items(dataset_id: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    limit = 100

    while True:
        dataset_url = f"{BASE_URL}/datasets/{dataset_id}/items"
        logger.info("Apify GET %s offset=%s limit=%s", dataset_url, offset, limit)
        items_resp = requests.get(
            dataset_url,
            headers=HEADERS,
            params={"limit": limit, "offset": offset, "clean": "true", "format": "json"},
            timeout=HTTP_TIMEOUT_SECS,
        )
        _log_response("Apify dataset items", items_resp)
        items_resp.raise_for_status()
        page_items = _safe_json(items_resp, "Apify dataset items")
        if not isinstance(page_items, list):
            raise RuntimeError(f"Respuesta inesperada de Apify dataset: {str(page_items)[:200]}")

        logger.info("dataset_page_received | dataset_id=%s | offset=%s | received=%s", dataset_id, offset, len(page_items))
        items.extend(page_items)
        if len(page_items) < limit:
            break
        offset += limit

    logger.info("Apify dataset items count=%s dataset_id=%s", len(items), dataset_id)
    return items


def _detect_next_page_token(payload: dict | list) -> str:
    if isinstance(payload, dict):
        token = payload.get("next_page_token") or payload.get("nextPageToken")
        if token:
            return str(token)
    return ""


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value.lower()).strip()


def _normalize_phone_for_dedupe(raw: str) -> str:
    if not raw:
        return ""
    digits = re.sub(r"\D+", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def _normalize_website_for_dedupe(raw: str) -> str:
    if not raw:
        return ""
    value = _normalize_text(raw)
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    return value.rstrip("/")


def _normalized_name(item: dict) -> str:
    return _normalize_text(item.get("title") or item.get("name") or "")


def _normalized_phone(item: dict) -> str:
    return _normalize_phone_for_dedupe(item.get("phone") or item.get("phoneUnformatted") or "")


def _normalized_website(item: dict) -> str:
    return _normalize_website_for_dedupe(item.get("website") or "")


def _dedupe_key(item: dict) -> tuple[str, str, str]:
    return (_normalized_name(item), _normalized_phone(item), _normalized_website(item))


def _keyword_score(keyword: str, country: str, languages: list[str]) -> float:
    stats = get_keyword_stats(keyword, country)
    leads = float(stats.get("leads_found", 0) or 0)
    dupes = float(stats.get("duplicates", 0) or 0)
    searches = float(stats.get("searches", 0) or 0)
    effectiveness = leads / max(1.0, leads + dupes)
    volume = min(1.0, leads / 25.0)
    activity = min(1.0, searches / 10.0)
    locale_bonus = 0.12 if any(keyword.lower() in language_keywords(lang) for lang in languages[:1]) else 0.0
    return round((0.55 * effectiveness) + (0.2 * volume) + (0.13 * activity) + locale_bonus, 4)


def _build_keywords(target: dict, business_type: str) -> list[str]:
    country = (target.get("country_norm") or "").upper()
    languages = country_languages(country)
    ordered: list[str] = []
    base = [business_type, f"best {business_type}", f"aesthetic {business_type}"]
    pools = [country_keywords(country)] + [language_keywords(lang) for lang in languages] + [SEARCH_KEYWORDS] + [base]
    scored: list[tuple[float, str]] = []
    seen = set()
    for pool in pools:
        for keyword in pool:
            key = keyword.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            scored.append((_keyword_score(keyword, country, languages), keyword))
    scored.sort(key=lambda item: item[0], reverse=True)
    ordered.extend([kw for _, kw in scored])
    logger.info("[KEYWORDS] country=%s languages=%s", country or "GLOBAL", ",".join(languages))
    for kw in ordered[:10]:
        logger.info('[KEYWORD_SCORE] "%s"=%.2f', kw, _keyword_score(kw, country, languages))
    return ordered


def _normalize_phone(raw: str, phone_prefix: str) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    # Si empieza por 0 sin ser 00, sustituir por el prefijo del país
    if cleaned.startswith("0") and not cleaned.startswith("00") and phone_prefix:
        cleaned = phone_prefix + " " + cleaned[1:]
    return cleaned


def _build_run_plan(business_type: str, zone_query: str, target: dict, requested_count: int, budget: SearchBudget) -> list[dict]:
    adaptive = build_adaptive_plan(zone_query, requested_count, budget=budget)
    if adaptive:
        points = [step["coord"] for step in adaptive]
    else:
        plan = build_geo_plan(zone_query, requested_count)
        points = plan_to_points(plan)
    points = points[:max(1, budget.max_zones)]
    keywords = _build_keywords(target, business_type)
    run_plan = [
        {
            "keyword": keyword,
            "coord": coord,
            "search_string": f"{keyword} in {zone_query} near {coord.latitude},{coord.longitude}",
        }
        for keyword, coord in product(keywords, points)
    ]
    if not run_plan:
        run_plan = [{"keyword": keyword, "coord": None, "search_string": f"{keyword} in {zone_query}"} for keyword in keywords]
    logger.info("[GEO] input=%s detected_type=%s subzones_generated=%s", zone_query, target.get("kind"), len(points))
    logger.info("[EXPANSION] subzones_generated=%s", len(points))
    return run_plan


def scrape_businesses(business_type: str, zone: str, requested_count: int, phone_prefix: str = "") -> list[dict]:
    """
    Busca negocios en Google Maps vía Apify.
    Devuelve lista normalizada con place_id, name, phone, address, zone,
    business_type, website, rating, reviews_count.
    """
    try:
        target = resolve_geo_target(zone)
    except Exception:
        logger.exception("[STOP] reason=geocoding_failure")
        target = {"raw": zone, "display_name": zone, "kind": "small_city", "city_norm": zone.lower(), "center": None, "bounds": [], "country_norm": "", "city_type": "medium_city"}
    zone_query = target.get("display_name") or target["raw"]

    budget = SearchBudget.for_request(requested_count)
    run_plan = _build_run_plan(business_type, zone_query, target, requested_count, budget)
    planned_keywords = list(dict.fromkeys(step.get("keyword", "") for step in run_plan if step.get("keyword")))
    planned_zones = list(dict.fromkeys(step.get("coord").name for step in run_plan if step.get("coord")))

    seen_keys = set()
    keyword_counters: dict[str, dict[str, int]] = {}
    results = []
    total_raw = 0
    discarded_location = 0
    discarded_duplicates = 0
    discarded_missing_name = 0
    discarded_invalid_coords = 0
    pages_visited = 0

    for index, step in enumerate(run_plan, start=1):
        if not budget.allow_zone():
            break
        if not budget.start_zone():
            break
        search_string = step["search_string"]
        coord = step.get("coord")
        radius = coord.radius if coord else None

        next_page_token = ""
        page = 0
        while True:
            if len(results) >= requested_count or budget.should_stop():
                break
            if not budget.allow_page(page):
                break
            page += 1
            pages_visited += 1
            logger.info("[SEARCH] keyword=%s coord=%s radius=%s page=%s results_received=%s", step.get("keyword"), coord.name if coord else "", radius, page, 0)
            logger.info("[ZONE] searching=%s", coord.name if coord else zone_query)
            payload = make_json_safe({
                "searchStringsArray": [search_string],
                "maxCrawledPlacesPerSearch": 100,
                "language": "en",
                "maxImages": 0,
                "maxReviews": 0,
                "exportPlaceUrls": False,
                "additionalInfo": False,
                "includeWebResults": False,
            })
            if next_page_token:
                payload["nextPageToken"] = next_page_token
            try:
                raw = _run_actor(payload)
            except Exception:
                logger.exception("[STOP] reason=provider_failure")
                budget.stop_reason = budget.stop_reason or "provider_failure"
                break
            budget.record_request(len(raw))
            total_raw += len(raw)
            logger.info("[SEARCH] keyword=%s coord=%s radius=%s page=%s results_received=%s", step.get("keyword"), coord.name if coord else "", radius, page, len(raw))

            before = len(raw)
            page_kept = 0
            for p in raw:
                place_id = (p.get("placeId") or "").strip()
                name = (p.get("title") or p.get("name") or "").strip()
                geo = extract_geo_fields(p)
                lat = geo.get("lat")
                lng = geo.get("lng")
                if not name:
                    discarded_missing_name += 1
                    continue
                if lat is not None and lng is not None:
                    try:
                        float(lat); float(lng)
                    except (TypeError, ValueError):
                        discarded_invalid_coords += 1
                        continue
                if not place_id:
                    place_id = f"{_normalized_name(p)}|{_normalized_phone(p)}|{_normalized_website(p)}"
                key = _dedupe_key(p)
                if key in seen_keys:
                    discarded_duplicates += 1
                    keyword_counters.setdefault(step.get("keyword", ""), {"leads_found": 0, "duplicates": 0})["duplicates"] += 1
                    continue
                accepted, reason = geo_match_reason(p, target)
                if not accepted:
                    discarded_location += 1
                    continue
                seen_keys.add(key)
                keyword_counters.setdefault(step.get("keyword", ""), {"leads_found": 0, "duplicates": 0})["leads_found"] += 1
                phone_raw = p.get("phone") or p.get("phoneUnformatted") or ""
                results.append({
                    "place_id": place_id,
                    "name": name,
                    "phone": _normalize_phone(phone_raw, phone_prefix),
                    "address": geo["address"],
                    "formatted_address": geo["formatted_address"],
                    "city": geo["city"],
                    "country": geo["country"],
                    "latitude": geo["lat"],
                    "longitude": geo["lng"],
                    "zone": zone,
                    "business_type": business_type.lower(),
                    "website": (p.get("website") or "").strip(),
                    "rating": p.get("totalScore") or None,
                    "reviews_count": p.get("reviewsCount") or 0,
                })
                page_kept += 1

            token = _detect_next_page_token(raw[0] if raw else {})
            logger.info("[PAGINATION] next_page_token=%s", bool(token))
            logger.info("[FILTER] discarded_missing_name=%s discarded_invalid_coords=%s", discarded_missing_name, discarded_invalid_coords)
            logger.info("[DEDUPE] before=%s after=%s duplicates_removed=%s", before, page_kept, discarded_duplicates)
            logger.info("[PROGRESS] total_accumulated=%s requested=%s", len(results), requested_count)

            if not token:
                budget.finish_zone(page_kept)
                break
            next_page_token = token
            time.sleep(2)

            if budget.early_stop_for_low_density():
                break

        if page > 0 and not next_page_token and budget.stop_reason == "":
            budget.stop("planner_exhausted", remaining_zones=max(0, len(run_plan) - index), pending_planners=max(0, len(planned_zones) - index), keywords_missing=max(0, len(planned_keywords) - len(keyword_counters)), requests_left=max(0, budget.max_requests - budget.requests_used))

        logger.info("[COVERAGE] searched_zones=%s/%s", index, len(run_plan))
        budget.finish_zone(page_kept)

        if len(results) >= requested_count:
            break
        if budget.should_stop():
            break

    remaining_zones = max(0, len(run_plan) - budget.zones_used)
    pending_planners = max(0, len(planned_zones) - budget.zones_used)
    pending_keywords = max(0, len(planned_keywords) - len(keyword_counters))
    requests_left = max(0, budget.max_requests - budget.requests_used)
    budget.log_metrics(remaining_zones=remaining_zones, pending_planners=pending_planners, pending_keywords=pending_keywords, requests_left=requests_left)
    country = (target.get("country_norm") or "").upper()
    for keyword, counters in keyword_counters.items():
        update_keyword_stats(keyword, country, leads_found=counters["leads_found"], duplicates=0, searches=1)
    if budget.stop_reason and budget.stop_reason != "planner_exhausted":
        logger.info("[STOP] reason=%s remaining_zones=%s pending_planners=%s keywords_missing=%s requests_left=%s", budget.stop_reason, remaining_zones, pending_planners, pending_keywords, requests_left)
    elif budget.stop_reason == "planner_exhausted":
        logger.info("[STOP] reason=planner_exhausted remaining_zones=%s pending_planners=%s keywords_missing=%s requests_left=%s", remaining_zones, pending_planners, pending_keywords, requests_left)
    logger.info(
        "[SUMMARY] total_raw=%s total_after_dedupe=%s duplicates_discarded=%s keywords_used=%s coordinates_used=%s pages_visited=%s completed_pct=%.2f",
        total_raw,
        len(results),
        discarded_duplicates,
        ",".join(_build_keywords(target, business_type)[:3]),
        ",".join(step["coord"].name for step in run_plan if step.get("coord")),
        pages_visited,
        min(100.0, (len(results) / requested_count * 100.0) if requested_count else 0.0),
    )
    return results
