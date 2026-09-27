"""Loads the approved company catalog (venues, menus, pricing rules) and docs.

The catalog is the ONLY source of prices and business rules. Nothing in the
LLM path is allowed to invent a number: every dollar figure in a proposal is
traceable to data/catalog.json via LineItem.rule.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    with open(DATA_DIR / "catalog.json") as f:
        return json.load(f)


def read_doc(rel_path: str) -> str:
    return (DATA_DIR / rel_path).read_text()


def venue(venue_id: str) -> dict:
    return load_catalog()["venues"][venue_id]


def menu(menu_id: str) -> dict:
    return load_catalog()["menus"][menu_id]


def pricing_rules() -> dict:
    return load_catalog()["pricing_rules"]


def match_venue_id(text: str) -> str | None:
    """Match free text against venue names and aliases."""
    lowered = text.lower()
    for vid, v in load_catalog()["venues"].items():
        candidates = [v["name"].lower(), *[a.lower() for a in v.get("aliases", [])]]
        if any(c in lowered for c in candidates):
            return vid
    return None


def select_menus(
    month: int | None,
    event_type: str | None,
    service_style: str | None,
    cocktail_hour: bool,
    preferences: list[str] | None = None,
) -> list[str]:
    """Pick dinner menu (+ cocktail add-on) from catalog metadata.

    Deterministic: filter by month/event/style, then prefer menus whose doc
    matches stated preferences, then lowest price. Never invents a menu.
    """
    catalog = load_catalog()
    prefs = [p.lower() for p in (preferences or [])]

    def score(mid: str, m: dict) -> tuple:
        pref_hits = 0
        if prefs:
            doc_text = read_doc(m["doc"]).lower() + " " + m["name"].lower()
            pref_hits = sum(1 for p in prefs if p in doc_text)
        return (-pref_hits, m["price_per_person"])

    candidates = {
        mid: m
        for mid, m in catalog["menus"].items()
        if (month is None or month in m["seasons_months"])
        and (event_type is None or event_type in m["event_types"])
        and (service_style is None or service_style in m["service_styles"])
        and mid != "cocktail-reception-classic"  # add-on handled below
    }
    selected: list[str] = []
    if service_style == "cocktail" and not candidates:
        selected.append("cocktail-reception-classic")
    elif candidates:
        selected.append(min(candidates, key=lambda mid: score(mid, candidates[mid])))
    if cocktail_hour and service_style != "cocktail":
        selected.append(catalog["pricing_rules"]["cocktail_hour_addon"]["menu_id"])
    return selected
