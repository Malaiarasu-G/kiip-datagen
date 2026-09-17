"""Fictitious name generation for every business entity in the synthetic data.

Centralized here so it's easy to audit that nothing resembles a real client
brand, retailer, or logistics-provider name (project decision: fully
fictitious data *values*; real column/table names are kept for schema realism).
"""
from __future__ import annotations

from typing import Callable, Set

import numpy as np

GBU_NAMES = ["Skin & Personal Care", "Everyday Wellness", "Active Living", "Family Health"]

FRANCHISE_THEMES = [
    "Radiant Skin", "Active Relief", "Digestive Comfort", "Eye & Vision Care",
    "Hair Renewal", "Sinus & Allergy", "Daily Vitality", "Oral Care",
    "Baby Essentials", "Sun & Outdoor",
]

CATEGORY_WORDS = [
    "Moisturizers", "Cleansers", "Pain Relief", "Cough & Cold", "Multivitamins",
    "Shampoo", "Conditioner", "Sunscreen", "Antacids", "First Aid",
]

CUSTOMER_SEGMENTS = ["Mass/Club", "Drug & Specialty", "Grocery", "Ecom", "FC&D", "Exports & All Others"]

DISTRIBUTION_CHANNEL_STATUS = [
    ("31", "Active Saleable"),
    ("32", "Discontinued Saleable"),
    ("33", "Obsolete"),
    ("37", "Obsolete with replace"),
]

_BRAND_ROOTS = [
    "Aven", "Nova", "Pure", "Vita", "Sooth", "Glo", "Cura", "Lumo", "Fresca",
    "Bota", "Calmi", "Verde", "Solis", "Aqua", "Terra", "Clarin", "Nectis",
]
_BRAND_SUFFIXES = ["derm", "lux", "well", "iva", "ora", "flex", "care", "plus", "tone", "fresh"]

_RETAILER_ROOTS = [
    "Metro", "Value", "Union", "Cedar", "Harbor", "Prime", "Green", "Northgate",
    "Fairview", "Ridgeline", "Coastal", "Summit", "Heritage", "Brookside", "Lakeside",
]
_RETAILER_SUFFIXES = ["Mart", "Grocers", "Foods", "Retail Co", "Superstore", "Wholesale Club", "Pharmacy", "Market"]

_LOGISTICS_ROOTS = ["Meridian", "Atlas", "Summit", "Harbor", "Vantage", "Cascade", "Union", "Beacon"]
_LOGISTICS_SUFFIXES = ["Logistics", "Distribution", "Freight Co", "Supply Chain"]
_CITIES = [
    "Rivergate", "Fontaine", "Palmwood", "Cedarville", "Norwood", "Fairhaven",
    "Ashport", "Millbrook", "Stonecreek", "Hollow Ridge",
]


class NamePool:
    """Wraps a `fn(rng) -> str` generator and disambiguates collisions with a
    numeric suffix, so repeated draws never silently collapse two entities
    onto the same name."""

    def __init__(self, fn: Callable[[np.random.Generator], str]):
        self._fn = fn
        self._seen: Set[str] = set()

    def next(self, rng: np.random.Generator) -> str:
        name = self._fn(rng)
        base, n = name, 2
        while name in self._seen:
            name = f"{base} {n}"
            n += 1
        self._seen.add(name)
        return name


def _brand_name(rng: np.random.Generator) -> str:
    return f"{rng.choice(_BRAND_ROOTS)}{rng.choice(_BRAND_SUFFIXES)}".title()


def _retailer_name(rng: np.random.Generator) -> str:
    return f"{rng.choice(_RETAILER_ROOTS)} {rng.choice(_RETAILER_SUFFIXES)}"


def _logistics_site_name(rng: np.random.Generator) -> str:
    operator = f"{rng.choice(_LOGISTICS_ROOTS)} {rng.choice(_LOGISTICS_SUFFIXES)}"
    city = rng.choice(_CITIES)
    return f"{operator} - {city}"


def new_brand_name_pool() -> NamePool:
    return NamePool(_brand_name)


def new_retailer_name_pool() -> NamePool:
    return NamePool(_retailer_name)


def new_logistics_site_name_pool() -> NamePool:
    return NamePool(_logistics_site_name)
