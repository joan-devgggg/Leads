"""
Persistencia ligera para cache, historial y rate limiting.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

from json_utils import make_json_safe

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).with_name("state_store.sqlite3")
_LOCK = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init() -> None:
    with _LOCK:
        with _conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    cache_value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS zone_stats (
                    zone_key TEXT PRIMARY KEY,
                    leads_found INTEGER NOT NULL DEFAULT 0,
                    duplicate_ratio REAL NOT NULL DEFAULT 0,
                    density REAL NOT NULL DEFAULT 0,
                    keyword_effectiveness TEXT NOT NULL DEFAULT '[]',
                    response_time REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS keyword_stats (
                    keyword TEXT NOT NULL,
                    country TEXT NOT NULL,
                    leads_found INTEGER NOT NULL DEFAULT 0,
                    duplicates INTEGER NOT NULL DEFAULT 0,
                    searches INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (keyword, country)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bucket TEXT PRIMARY KEY,
                    last_request REAL NOT NULL DEFAULT 0,
                    tokens REAL NOT NULL DEFAULT 1
                )
                """
            )


def cache_get(key: str):
    init()
    with _LOCK, _conn() as conn:
        row = conn.execute("SELECT cache_value FROM cache WHERE cache_key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None


def cache_set(key: str, value) -> None:
    init()
    payload = json.dumps(make_json_safe(value), ensure_ascii=True)
    with _LOCK, _conn() as conn:
        conn.execute(
            "INSERT INTO cache(cache_key, cache_value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(cache_key) DO UPDATE SET cache_value=excluded.cache_value, updated_at=excluded.updated_at",
            (key, payload, time.time()),
        )


def cache_exists(key: str) -> bool:
    return cache_get(key) is not None


def get_zone_stats(zone_key: str) -> dict:
    init()
    with _LOCK, _conn() as conn:
        row = conn.execute("SELECT * FROM zone_stats WHERE zone_key = ?", (zone_key,)).fetchone()
        return dict(row) if row else {
            "zone_key": zone_key,
            "leads_found": 0,
            "duplicate_ratio": 0,
            "density": 0,
            "keyword_effectiveness": [],
            "response_time": 0,
        }


def update_zone_stats(zone_key: str, *, leads_found: int = 0, duplicate_ratio: float = 0.0, density: float = 0.0, keywords=None, response_time: float = 0.0) -> None:
    init()
    current = get_zone_stats(zone_key)
    current["leads_found"] = int(current.get("leads_found", 0)) + int(leads_found)
    current["duplicate_ratio"] = duplicate_ratio if duplicate_ratio else float(current.get("duplicate_ratio", 0))
    current["density"] = density if density else float(current.get("density", 0))
    current["keyword_effectiveness"] = json.dumps(make_json_safe(keywords or []), ensure_ascii=True)
    current["response_time"] = response_time if response_time else float(current.get("response_time", 0))
    with _LOCK, _conn() as conn:
        conn.execute(
            """
            INSERT INTO zone_stats(zone_key, leads_found, duplicate_ratio, density, keyword_effectiveness, response_time, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(zone_key) DO UPDATE SET
                leads_found=excluded.leads_found,
                duplicate_ratio=excluded.duplicate_ratio,
                density=excluded.density,
                keyword_effectiveness=excluded.keyword_effectiveness,
                response_time=excluded.response_time,
                updated_at=excluded.updated_at
            """,
            (zone_key, current["leads_found"], current["duplicate_ratio"], current["density"], current["keyword_effectiveness"], current["response_time"], time.time()),
        )


def get_keyword_stats(keyword: str, country: str) -> dict:
    init()
    with _LOCK, _conn() as conn:
        row = conn.execute(
            "SELECT * FROM keyword_stats WHERE keyword = ? AND country = ?",
            (keyword, country),
        ).fetchone()
        return dict(row) if row else {
            "keyword": keyword,
            "country": country,
            "leads_found": 0,
            "duplicates": 0,
            "searches": 0,
        }


def update_keyword_stats(keyword: str, country: str, *, leads_found: int = 0, duplicates: int = 0, searches: int = 1) -> None:
    init()
    current = get_keyword_stats(keyword, country)
    current["leads_found"] = int(current.get("leads_found", 0)) + int(leads_found)
    current["duplicates"] = int(current.get("duplicates", 0)) + int(duplicates)
    current["searches"] = int(current.get("searches", 0)) + int(searches)
    with _LOCK, _conn() as conn:
        conn.execute(
            """
            INSERT INTO keyword_stats(keyword, country, leads_found, duplicates, searches, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(keyword, country) DO UPDATE SET
                leads_found=excluded.leads_found,
                duplicates=excluded.duplicates,
                searches=excluded.searches,
                updated_at=excluded.updated_at
            """,
            (keyword, country, current["leads_found"], current["duplicates"], current["searches"], time.time()),
        )


class RateLimitError(RuntimeError):
    pass


def acquire(bucket: str, min_interval: float) -> None:
    init()
    with _LOCK, _conn() as conn:
        row = conn.execute("SELECT last_request FROM rate_limits WHERE bucket = ?", (bucket,)).fetchone()
        now = time.time()
        last = float(row[0]) if row else 0.0
        wait = min_interval - (now - last)
        if wait > 0:
            time.sleep(wait)
        conn.execute(
            "INSERT INTO rate_limits(bucket, last_request, tokens) VALUES (?, ?, 1) "
            "ON CONFLICT(bucket) DO UPDATE SET last_request=excluded.last_request",
            (bucket, time.time()),
        )
