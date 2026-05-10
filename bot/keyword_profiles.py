"""
Perfiles de keywords internacionalizados por país e idioma.
"""
from __future__ import annotations

from dataclasses import dataclass


COUNTRY_LANGUAGE_PROFILE = {
    "AR": ["es", "en"],
    "ES": ["es", "en"],
    "BR": ["pt", "en"],
    "FR": ["fr", "en"],
    "AE": ["en", "ar"],
}

GLOBAL_KEYWORDS = {
    "en": ["aesthetic clinic", "beauty clinic", "cosmetic clinic", "skin clinic", "medical spa"],
    "es": ["clínica estética", "medicina estética", "centro de estética", "cirugía plástica", "dermatología estética", "depilación láser", "estética facial", "beauty center"],
    "pt": ["clínica estética", "medicina estética", "clínica de beleza", "dermatologia estética"],
    "fr": ["clinique esthétique", "médecine esthétique", "chirurgie esthétique"],
    "ar": ["عيادة تجميل", "عيادة طبية تجميلية", "مركز تجميل", "جراحة تجميل", "جلدية تجميلية"],
}

COUNTRY_KEYWORDS = {
    "AR": ["clínica estética", "medicina estética", "centro de estética", "depilación láser", "aesthetic clinic"],
    "ES": ["clínica estética", "medicina estética", "centro de estética", "dermatología estética", "aesthetic clinic"],
    "BR": ["clínica estética", "clínica de beleza", "medicina estética", "dermatologia estética", "aesthetic clinic"],
    "FR": ["clinique esthétique", "médecine esthétique", "chirurgie esthétique", "aesthetic clinic"],
    "AE": ["aesthetic clinic", "beauty clinic", "cosmetic clinic", "عيادة تجميل", "مركز تجميل", "medical spa"],
}


def country_languages(country_code: str) -> list[str]:
    return COUNTRY_LANGUAGE_PROFILE.get((country_code or "").upper(), ["en"])


def country_keywords(country_code: str) -> list[str]:
    return COUNTRY_KEYWORDS.get((country_code or "").upper(), GLOBAL_KEYWORDS["en"])


def language_keywords(language: str) -> list[str]:
    return GLOBAL_KEYWORDS.get((language or "").lower(), [])


@dataclass(frozen=True)
class KeywordCandidate:
    keyword: str
    language: str
    source: str
    score: float
