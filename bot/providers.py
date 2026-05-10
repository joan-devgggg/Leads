"""
Arquitectura modular de proveedores de leads.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLeadProvider(ABC):
    name = "base"

    @abstractmethod
    def search(self, business_type: str, zone: str, requested_count: int, phone_prefix: str = "") -> list[dict]:
        raise NotImplementedError


class GoogleMapsProvider(BaseLeadProvider):
    name = "google_maps"

    def search(self, business_type: str, zone: str, requested_count: int, phone_prefix: str = "") -> list[dict]:
        from scraper import scrape_businesses as _scrape

        return _scrape(business_type, zone, requested_count, phone_prefix)

