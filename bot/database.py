"""
Operaciones de Supabase: filtrar duplicados y guardar negocios enviados.
"""
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY
import unicodedata
import re
import logging
from state_store import update_zone_stats

_client = None
logger = logging.getLogger(__name__)

def _get_client():
    global _client
    if _client is None:
        import urllib.parse
        parsed = urllib.parse.urlparse(SUPABASE_URL)
        logger.info("supabase_host=%s scheme=%s", parsed.hostname, parsed.scheme)
        if not parsed.hostname or parsed.scheme != "https":
            raise RuntimeError(f"SUPABASE_URL mal formada: '{SUPABASE_URL}'")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def _with_timeout(query):
    return query.execute()


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _normalize_phone(text: str) -> str:
    return re.sub(r"\D+", "", text or "")


def _normalize_website(text: str) -> str:
    text = _normalize_text(text)
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    return text.rstrip("/")


def _dedupe_key(item: dict) -> tuple[str, str, str]:
    return (
        _normalize_text(item.get("place_id", "")),
        _normalize_text(item.get("name", "")),
        _normalize_phone(item.get("phone", "")),
        _normalize_website(item.get("website", "")),
    )


def filter_new(candidates: list[dict]) -> list[dict]:
    """Devuelve solo los negocios cuyo dedupe normalizado no está ya en Supabase."""
    if not candidates:
        return []

    db = _get_client()
    candidate_keys = [_dedupe_key(b) for b in candidates]
    unique_keys = list(dict.fromkeys(candidate_keys))
    if len(unique_keys) != len(candidate_keys):
        logger.info("duplicates_descartados_input=%s", len(candidate_keys) - len(unique_keys))

    # Use raw (non-normalized) values for Supabase queries — the DB stores raw data.
    # Normalized keys are only used for in-memory comparison after retrieval.
    place_ids_raw = sorted({b.get("place_id", "") for b in candidates if b.get("place_id")})
    names_raw = sorted({b.get("name", "") for b in candidates if b.get("name")})
    phones_raw = sorted({b.get("phone", "") for b in candidates if b.get("phone")})
    websites_raw = sorted({b.get("website", "") for b in candidates if b.get("website")})

    existing_rows = []
    if place_ids_raw:
        existing_rows.extend(_with_timeout(db.table("negocios").select("place_id,name,phone,website").in_("place_id", place_ids_raw)).data)
    if names_raw:
        existing_rows.extend(_with_timeout(db.table("negocios").select("place_id,name,phone,website").in_("name", names_raw)).data)
    if phones_raw:
        existing_rows.extend(_with_timeout(db.table("negocios").select("place_id,name,phone,website").in_("phone", phones_raw)).data)
    if websites_raw:
        existing_rows.extend(_with_timeout(db.table("negocios").select("place_id,name,phone,website").in_("website", websites_raw)).data)
    existing_keys = {_dedupe_key(row) for row in existing_rows}

    filtered = [b for b in candidates if _dedupe_key(b) not in existing_keys]
    logger.info("total_antes_dedupe=%s total_despues_dedupe=%s", len(candidates), len(filtered))
    return filtered


_SCHEMA_FIELDS = frozenset({
    "place_id", "name", "phone", "address", "formatted_address",
    "city", "country", "latitude", "longitude",
    "zone", "business_type", "website", "rating", "reviews_count",
})


def save(businesses: list[dict]) -> None:
    """Guarda los negocios en Supabase. Ignora duplicados silenciosamente."""
    if not businesses:
        return
    db = _get_client()
    payload = []
    for business in businesses:
        item = {k: v for k, v in business.items() if k in _SCHEMA_FIELDS}
        item["zone"] = _normalize_text(item.get("zone", ""))
        item["business_type"] = _normalize_text(item.get("business_type", ""))
        payload.append(item)
    _with_timeout(db.table("negocios").upsert(payload, ignore_duplicates=True))
    if payload:
        zone = payload[0].get("zone", "")
        update_zone_stats(zone, leads_found=len(payload), density=float(len(payload)))


def count_sent(zone: str, business_type: str) -> int:
    """Cuántos negocios de ese tipo y zona ya fueron enviados."""
    db = _get_client()
    resp = _with_timeout(
        db.table("negocios")
        .select("id", count="exact")
        .eq("zone", _normalize_text(zone))
        .eq("business_type", _normalize_text(business_type))
    )
    return resp.count or 0


def is_authorized(telegram_user_id: int) -> bool:
    """Comprueba si el user ID está en la whitelist de usuarios_autorizados."""
    db = _get_client()
    resp = _with_timeout(
        db.table("usuarios_autorizados")
        .select("telegram_user_id", count="exact")
        .eq("telegram_user_id", telegram_user_id)
    )
    return (resp.count or 0) > 0
