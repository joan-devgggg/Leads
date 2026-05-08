"""
Wrapper de Apify Google Maps Scraper, generalizado desde scrape_clinicas_dubai.py.
"""
import time
import requests
from config import APIFY_API_TOKEN, APIFY_ACTOR_ID, APIFY_TIMEOUT_SECS

BASE_URL = "https://api.apify.com/v2"
HEADERS  = {"Authorization": f"Bearer {APIFY_API_TOKEN}"}


def _run_actor(run_input: dict) -> list[dict]:
    r = requests.post(
        f"{BASE_URL}/acts/{APIFY_ACTOR_ID}/runs",
        headers=HEADERS,
        json=run_input,
        params={"timeout": APIFY_TIMEOUT_SECS},
    )
    r.raise_for_status()
    run_id = r.json()["data"]["id"]

    deadline = time.time() + APIFY_TIMEOUT_SECS
    while time.time() < deadline:
        s = requests.get(f"{BASE_URL}/actor-runs/{run_id}", headers=HEADERS).json()["data"]
        status = s["status"]
        if status == "SUCCEEDED":
            dataset_id = s["defaultDatasetId"]
            items = requests.get(
                f"{BASE_URL}/datasets/{dataset_id}/items",
                headers=HEADERS,
                params={"limit": 500, "clean": "true", "format": "json"},
            ).json()
            if not isinstance(items, list):
                raise RuntimeError(f"Respuesta inesperada de Apify dataset: {str(items)[:200]}")
            return items
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Apify terminó con estado: {status}")
        time.sleep(8)
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
    per_search = max(20, (max_results + 10) // 2)
    run_input = {
        "searchStringsArray": [
            f"{business_type} {zone}",
            f"best {business_type} in {zone}",
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
    results = []
    for p in raw:
        place_id = (p.get("placeId") or "").strip()
        name = (p.get("title") or "").strip()
        if not place_id or not name or place_id in seen_ids:
            continue
        seen_ids.add(place_id)

        phone_raw = p.get("phone") or p.get("phoneUnformatted") or ""
        results.append({
            "place_id":      place_id,
            "name":          name,
            "phone":         _normalize_phone(phone_raw, phone_prefix),
            "address":       (p.get("address") or "").strip(),
            "zone":          (p.get("neighborhood") or p.get("city") or zone).strip(),
            "business_type": business_type.lower(),
            "website":       (p.get("website") or "").strip(),
            "rating":        p.get("totalScore") or None,
            "reviews_count": p.get("reviewsCount") or 0,
        })

    return results
