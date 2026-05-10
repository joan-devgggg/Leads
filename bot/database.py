"""
Operaciones de Supabase: filtrar duplicados y guardar negocios enviados.
"""
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def _with_timeout(query, timeout_secs: float = 45):
    try:
        return query.execute(timeout=timeout_secs)
    except TypeError:
        return query.execute()


def filter_new(candidates: list[dict]) -> list[dict]:
    """Devuelve solo los negocios cuyo place_id no está ya en Supabase."""
    if not candidates:
        return []

    db = _get_client()
    place_ids = [b["place_id"] for b in candidates]

    resp = _with_timeout(db.table("negocios").select("place_id").in_("place_id", place_ids))
    already_sent = {row["place_id"] for row in resp.data}

    return [b for b in candidates if b["place_id"] not in already_sent]


def save(businesses: list[dict]) -> None:
    """Guarda los negocios en Supabase. Ignora duplicados silenciosamente."""
    if not businesses:
        return
    db = _get_client()
    _with_timeout(db.table("negocios").upsert(businesses, ignore_duplicates=True))


def count_sent(zone: str, business_type: str) -> int:
    """Cuántos negocios de ese tipo y zona ya fueron enviados."""
    db = _get_client()
    resp = _with_timeout(
        db.table("negocios")
        .select("id", count="exact")
        .eq("zone", zone.lower())
        .eq("business_type", business_type.lower())
    )
    return resp.count or 0
