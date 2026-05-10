"""
Planner jerárquico de cobertura por país/region/city con scoring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from geo_utils import SearchPoint, _norm, build_geo_plan, resolve_geo_target
from json_utils import make_json_safe
from search_budget import SearchBudget
from state_store import cache_get, cache_set, get_zone_stats

logger = logging.getLogger(__name__)

_BIG_COUNTRIES = {
    "spain": ["Madrid", "Barcelona", "Valencia", "Sevilla", "Málaga", "Bilbao", "Zaragoza", "Alicante", "Murcia", "Palma"],
    "argentina": ["Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata", "Mar del Plata"],
    "united states": ["New York", "Los Angeles", "Chicago", "Houston", "Miami", "Dallas", "San Francisco", "Boston", "Seattle", "Atlanta"],
    "india": ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune"],
    "mexico": ["Mexico City", "Guadalajara", "Monterrey", "Puebla", "Tijuana", "Querétaro"],
    "brazil": ["São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza", "Belo Horizonte"],
}


@dataclass(frozen=True)
class PlanNode:
    name: str
    zone: str
    score: float
    target: dict
    points: list


def _score_zone(zone: str, requested_count: int) -> float:
    target = resolve_geo_target(zone)
    stats = get_zone_stats(_norm(zone))
    city_type = target.get("city_type") or "medium_city"
    pop = {"country": 1.0, "region": 0.95, "metro_area": 0.98, "mega_city": 0.97, "medium_city": 0.7, "small_city": 0.35}.get(target.get("kind"), 0.5)
    density = min(1.0, float(stats.get("density", 0)) / 100.0)
    previous = min(1.0, float(stats.get("leads_found", 0)) / max(1, requested_count))
    importance = {"mega_city": 1.0, "metro_area": 0.95, "medium_city": 0.7, "small_city": 0.35}.get(city_type, 0.5)
    return round(pop * 0.35 + density * 0.25 + previous * 0.15 + importance * 0.25, 4)


def build_country_plan(zone: str, requested_count: int, budget: SearchBudget | None = None) -> dict:
    target = resolve_geo_target(zone)
    country = _norm(target.get("country") or target.get("raw") or zone)
    if country not in _BIG_COUNTRIES:
        return build_geo_plan(zone, requested_count)

    cities = _BIG_COUNTRIES[country]
    if requested_count <= 75:
        cities = cities[:3]
    elif requested_count <= 500:
        cities = cities[:6]

    nodes = []
    for city in cities:
        if budget and len(nodes) >= budget.max_zones:
            break
        city_score = _score_zone(city, requested_count)
        plan = build_geo_plan(city, requested_count)
        nodes.append(PlanNode(city, city, city_score, plan["target"], plan["points"]))

    nodes.sort(key=lambda n: n.score, reverse=True)
    serialized_nodes = []
    for n in nodes:
        try:
            points = [make_json_safe(p) for p in n.points]
        except Exception:
            logger.exception("[PLANNER] point_serialization_failed zone=%s node=%s points_type=%s", zone, n.name, [type(p).__name__ for p in n.points])
            raise
        serialized_nodes.append({"name": n.name, "zone": n.zone, "score": n.score, "target": n.target, "points": points})

    payload = {
        "target": target,
        "nodes": serialized_nodes,
    }
    cache_set(f"country_plan::{_norm(zone)}::{requested_count}", make_json_safe(payload))
    logger.info("[PLANNER] country=%s cities_selected=%s", country, len(nodes))
    for node in nodes[:5]:
        logger.info("[SCORE] %s=%.2f", node.name, node.score)
    return payload


def build_adaptive_plan(zone: str, requested_count: int, budget: SearchBudget | None = None) -> list[dict]:
    cached = cache_get(f"country_plan::{_norm(zone)}::{requested_count}")
    if cached:
        nodes = cached.get("nodes", [])
    else:
        nodes = build_country_plan(zone, requested_count, budget=budget).get("nodes", [])
    run_plan = []
    for node in nodes:
        points = node.get("points", [])
        take = len(points)
        if requested_count <= 50:
            take = min(take, 3)
        elif requested_count <= 500:
            take = min(take, 8)
        if budget:
            remaining = max(0, budget.max_zones - len(run_plan))
            take = min(take, remaining)
        selected = points[:take]
        for point in selected:
            run_plan.append({"zone": node["zone"], "score": node["score"], "coord": SearchPoint(**point), "keyword_hint": node["name"]})
    return run_plan
