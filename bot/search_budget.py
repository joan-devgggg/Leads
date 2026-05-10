"""
Control central de presupuesto y condiciones de parada para búsquedas.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from config import (
    MAX_API_CALLS,
    MAX_CONSECUTIVE_EMPTY_RESULTS,
    MAX_EMPTY_ZONES,
    MAX_PAGES_PER_ZONE,
    MAX_REQUESTS_PER_RUN,
    MAX_RUNTIME_SECONDS,
    MAX_ZONES_PER_SEARCH,
)

logger = logging.getLogger(__name__)


def _scaled_limit(base: int, requested_count: int, *, floor: int, ceiling: int, pivot: int = 500) -> int:
    if requested_count <= 0:
        return floor
    scale = max(1.0, requested_count / float(pivot))
    return max(floor, min(ceiling, int(base * scale)))


@dataclass
class SearchBudget:
    requested_count: int
    started_at: float = field(default_factory=time.time)
    max_zones: int = 0
    max_requests: int = 0
    max_runtime_seconds: int = 0
    max_api_calls: int = 0
    max_pages_per_zone: int = 0
    max_empty_zones: int = 0
    max_consecutive_empty_results: int = 0
    requests_used: int = 0
    api_calls_used: int = 0
    pages_used: int = 0
    zones_used: int = 0
    leads_found: int = 0
    empty_zones: int = 0
    consecutive_empty_zones: int = 0
    consecutive_empty_results: int = 0
    stop_reason: str = ""
    stop_details: dict = field(default_factory=dict)

    @classmethod
    def for_request(cls, requested_count: int) -> "SearchBudget":
        return cls(
            requested_count=requested_count,
            max_zones=_scaled_limit(MAX_ZONES_PER_SEARCH, requested_count, floor=8, ceiling=400),
            max_requests=_scaled_limit(MAX_REQUESTS_PER_RUN, requested_count, floor=20, ceiling=2500),
            max_runtime_seconds=_scaled_limit(MAX_RUNTIME_SECONDS, requested_count, floor=60, ceiling=7200),
            max_api_calls=_scaled_limit(MAX_API_CALLS, requested_count, floor=20, ceiling=1000),
            max_pages_per_zone=max(1, min(MAX_PAGES_PER_ZONE if requested_count <= 200 else MAX_PAGES_PER_ZONE * 2 + 1, 12)),
            max_empty_zones=max(1, min(MAX_EMPTY_ZONES if requested_count <= 500 else MAX_EMPTY_ZONES * 3 // 2 + 1, 60)),
            max_consecutive_empty_results=max(1, min(MAX_CONSECUTIVE_EMPTY_RESULTS if requested_count <= 500 else MAX_CONSECUTIVE_EMPTY_RESULTS * 3 // 2 + 1, 60)),
        )

    @property
    def runtime_seconds(self) -> float:
        return time.time() - self.started_at

    def log_metrics(self, *, remaining_zones: int = 0, pending_planners: int = 0, pending_keywords: int = 0, requests_left: int = 0) -> None:
        logger.info("[BUDGET] requests_used=%s/%s api_calls_used=%s/%s pages_used=%s zones_used=%s/%s", self.requests_used, self.max_requests, self.api_calls_used, self.max_api_calls, self.pages_used, self.zones_used, self.max_zones)
        logger.info("[TIME] runtime=%ss max_runtime=%ss", int(self.runtime_seconds), self.max_runtime_seconds)
        logger.info("[EFFICIENCY] leads_per_request=%.2f", (self.leads_found / max(1, self.requests_used)))
        logger.info("[EMPTY] empty_zones=%s consecutive_empty_zones=%s consecutive_empty_results=%s", self.empty_zones, self.consecutive_empty_zones, self.consecutive_empty_results)
        logger.info("[REMAINING] zones=%s planners=%s keywords=%s requests=%s", remaining_zones, pending_planners, pending_keywords, requests_left)

    def _stop(self, reason: str) -> bool:
        if not self.stop_reason:
            self.stop_reason = reason
        return True

    def stop(self, reason: str, **details) -> bool:
        if not self.stop_reason:
            self.stop_reason = reason
            self.stop_details = {k: v for k, v in details.items() if v is not None}
            detail_str = " ".join(f"{k}={v}" for k, v in self.stop_details.items())
            logger.info("[STOP] reason=%s%s%s", reason, " " if detail_str else "", detail_str)
        return True

    def should_stop(self) -> bool:
        if self.leads_found >= self.requested_count > 0:
            return self.stop("requested_count")
        if self.runtime_seconds >= self.max_runtime_seconds:
            return self.stop("max_runtime")
        if self.requests_used >= self.max_requests:
            return self.stop("max_requests")
        if self.api_calls_used >= self.max_api_calls:
            return self.stop("max_api_calls")
        if self.zones_used >= self.max_zones:
            return self.stop("max_zones")
        if self.empty_zones >= self.max_empty_zones:
            return self.stop("max_empty_zones")
        if self.consecutive_empty_results >= self.max_consecutive_empty_results:
            return self.stop("max_consecutive_empty_results")
        return False

    def allow_zone(self) -> bool:
        return not self.should_stop()

    def start_zone(self) -> bool:
        if self.zones_used >= self.max_zones:
            self._stop("max_zones")
            return False
        self.zones_used += 1
        return True

    def allow_page(self, pages_in_zone: int) -> bool:
        if pages_in_zone >= self.max_pages_per_zone:
            self.stop("max_pages_per_zone")
            return False
        return not self.should_stop()

    def record_request(self, results_received: int = 0) -> None:
        self.requests_used += 1
        self.api_calls_used += 1
        self.pages_used += 1
        self.leads_found += max(0, results_received)
        if results_received <= 0:
            self.consecutive_empty_results += 1
        else:
            self.consecutive_empty_results = 0
            self.consecutive_empty_zones = 0

    def finish_zone(self, leads_in_zone: int) -> None:
        if leads_in_zone <= 0:
            self.empty_zones += 1
            self.consecutive_empty_zones += 1
        else:
            self.consecutive_empty_zones = 0

    def early_stop_for_low_density(self) -> bool:
        if self.zones_used < 6:
            return False
        empty_ratio = self.empty_zones / max(1, self.zones_used)
        lead_density = self.leads_found / max(1, self.requests_used)
        if self.empty_zones >= 4 and empty_ratio >= 0.5 and self.leads_found <= max(4, self.zones_used // 3) and lead_density <= 0.6:
            return self.stop("low_density", empty_zones=self.empty_zones, zones_used=self.zones_used, leads_found=self.leads_found, empty_ratio=round(empty_ratio, 2), lead_density=round(lead_density, 2))
        return False
