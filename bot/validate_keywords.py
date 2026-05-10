"""
Validación offline del sistema de keywords por país.
"""
from __future__ import annotations

from keyword_profiles import country_languages
from scraper import _build_keywords


CASES = [
    ("AR", "Buenos Aires"),
    ("ES", "Madrid"),
    ("BR", "São Paulo"),
    ("FR", "Paris"),
    ("AE", "Dubai"),
]


def main() -> None:
    for country, zone in CASES:
        target = {"country_norm": country.lower()}
        keywords = _build_keywords(target, "aesthetic clinic")
        print(f"country={country} zone={zone} languages={','.join(country_languages(country))}")
        print(", ".join(keywords[:8]))
        print()


if __name__ == "__main__":
    main()
