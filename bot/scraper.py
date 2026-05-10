"""
Wrapper de Apify Google Maps Scraper, generalizado desde scrape_clinicas_dubai.py.
"""
import time
import logging
import requests
from config import APIFY_API_TOKEN, APIFY_ACTOR_ID, APIFY_TIMEOUT_SECS, HTTP_TIMEOUT_SECS
from geo_utils import extract_geo_fields, geo_match_reason, parse_target_location

BASE_URL = "https://api.apify.com/v2"
HEADERS  = {"Authorization": f"Bearer {APIFY_API_TOKEN}"}

logger = logging.getLogger(__name__)


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
        json=run_input,
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
            dataset_url = f"{BASE_URL}/datasets/{dataset_id}/items"
            logger.info("Apify GET %s", dataset_url)
            items_resp = requests.get(
                dataset_url,
                headers=HEADERS,
                params={"limit": 500, "clean": "true", "format": "json"},
                timeout=HTTP_TIMEOUT_SECS,
            )
            _log_response("Apify dataset items", items_resp)
            items_resp.raise_for_status()
            items = _safe_json(items_resp, "Apify dataset items")
            if not isinstance(items, list):
                raise RuntimeError(f"Respuesta inesperada de Apify dataset: {str(items)[:200]}")
            logger.info("Apify dataset items count=%s dataset_id=%s", len(items), dataset_id)
            return items
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify terminó con estado: {status}")
        time.sleep(5)
    raise TimeoutError("El actor de Apify no terminó a tiempo.")


def _normalize_phone(raw: str, phone_prefix: str) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    # Si empieza por 0 sin ser 00, sustituir por el prefijo del país
    if cleaned.startswith("0") and not cleaned.startswith("00") and phone_prefix:
        cleaned = phone_prefix + " " + cleaned[1:]
    return cleaned


def scrape_businesses(business_type: str, zone: str, max_results: int, phone_prefix: str = "") -> list[dict]:
    """
    Busca negocios en Google Maps vía Apify.
    Devuelve lista normalizada con place_id, name, phone, address, zone,
    business_type, website, rating, reviews_count.
    """
    target = parse_target_location(zone)
    zone_query = target["raw"]
    if target["city"] and target["country"]:
        zone_query = f"{target['city']}, {target['country']}"

    per_search = max(20, (max_results + 10) // 2)
    run_input = {
        "searchStringsArray": [
            f"{business_type} in {zone_query}",
            f"{business_type} in {target['city']}, {target['country']}" if target["country"] else f"{business_type} in {target['city']}",
            f"best {business_type} in {zone_query}",
        ],
        "maxCrawledPlacesPerSearch": per_search,
        "language": "en",
        "maxImages": 0,
        "maxReviews": 0,
        "exportPlaceUrls": False,
        "additionalInfo": False,
        "includeWebResults": False,
    }

    raw = _run_actor(run_input)

    seen_ids = set()
    discarded_location = 0
    results = []
    for p in raw:
        place_id = (p.get("placeId") or "").strip()
        name = (p.get("title") or "").strip()
        if not place_id or not name or place_id in seen_ids:
            continue
        seen_ids.add(place_id)

        accepted, reason = geo_match_reason(p, target)
        if not accepted:
            discarded_location += 1
            logger.info(
                "rejected_geo | result=%s | place_id=%s | name=%s | target=%s | geo=%s",
                reason,
                place_id,
                name,
                zone,
                extract_geo_fields(p),
            )
            continue

        phone_raw = p.get("phone") or p.get("phoneUnformatted") or ""
        geo = extract_geo_fields(p)
        results.append({
            "place_id":      place_id,
            "name":          name,
            "phone":         _normalize_phone(phone_raw, phone_prefix),
            "address":       geo["address"],
            "formatted_address": geo["formatted_address"],
            "city":          geo["city"],
            "country":       geo["country"],
            "latitude":      geo["lat"],
            "longitude":     geo["lng"],
            "zone":          zone,
            "business_type": business_type.lower(),
            "website":       (p.get("website") or "").strip(),
            "rating":        p.get("totalScore") or None,
            "reviews_count": p.get("reviewsCount") or 0,
        })
        logger.info(
            "accepted_geo | result=%s | place_id=%s | name=%s | target=%s | geo=%s",
            reason,
            place_id,
            name,
            zone,
            geo,
        )

    logger.info(
        "Filtered by location | target=%s | raw=%s | kept=%s | discarded_location=%s",
        zone,
        len(raw),
        len(results),
        discarded_location,
    )
    return results
