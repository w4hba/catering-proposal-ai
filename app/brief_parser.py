"""Turn a free-text event brief into a structured EventBrief.

Two paths:
- Claude (if ANTHROPIC_API_KEY is set): tool-use structured extraction, which
  handles arbitrary phrasing. Output is still validated against the catalog —
  the model can only pick venues/menus that exist.
- Deterministic fallback: regex + keyword extraction, so the demo runs
  end-to-end with no API key and tests stay hermetic.
"""
from __future__ import annotations

import calendar
import os
import re
from datetime import date

from .catalog import match_venue_id
from .models import EventBrief

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})

_EVENT_TYPES = {
    "wedding": ["wedding", "bride", "groom"],
    "corporate": ["corporate", "company", "offsite", "off-site", "holiday party", "team", "conference", "meeting", "client dinner"],
    "gala": ["gala", "fundraiser", "benefit", "awards"],
    "social": ["birthday", "anniversary", "shower", "bar mitzvah", "bat mitzvah", "quincea", "retirement", "graduation"],
}
_STYLES = {
    "plated": ["plated", "seated dinner", "sit-down", "sit down", "three-course", "3-course"],
    "stations": ["stations", "food station", "grazing"],
    "buffet": ["buffet"],
    "cocktail": ["cocktail-style", "cocktail style", "standing reception", "heavy hors", "passed apps only"],
}


def parse_brief(text: str, client_name: str | None = None) -> tuple[EventBrief, str]:
    """Returns (brief, parser_used) where parser_used is 'claude' or 'rules-only'."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            brief = _parse_with_claude(text, client_name)
            return brief, "claude"
        except Exception:
            pass  # fall back rather than block the salesperson
    return _parse_with_rules(text, client_name), "rules-only"


# --------------------------------------------------------------------------- fallback
def _parse_with_rules(text: str, client_name: str | None) -> EventBrief:
    lowered = text.lower()
    brief = EventBrief(raw_text=text)
    if client_name:
        brief.client_name = client_name
    else:
        # Prefix is case-insensitive but the captured name must be capitalized,
        # so "The client is planning a 150-person..." doesn't capture a verb.
        m = re.search(
            r"(?i:client\s+(?:name is|is|:)?)\s*([A-Z][\w'&. -]+?)(?:\s+(?:is|are|would|wants|plans)|[,.]|$)",
            text,
        )
        if m:
            brief.client_name = m.group(1).strip()

    m = re.search(r"(\d{2,4})[\s-]*(?:person|guest|people|pax|attendee)", lowered)
    if m:
        brief.guest_count = int(m.group(1))

    for name, num in _MONTHS.items():
        if re.search(rf"\b{name}\b", lowered):
            brief.event_month = num
            break
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text) or re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", text)
    if m:
        g = m.groups()
        y, mo, d = (int(g[0]), int(g[1]), int(g[2])) if len(g[0]) == 4 else (int(g[2]), int(g[0]), int(g[1]))
        try:
            brief.event_date = date(y, mo, d)
            brief.event_month = mo
        except ValueError:
            pass

    brief.venue_id = match_venue_id(text)

    for etype, kws in _EVENT_TYPES.items():
        if any(k in lowered for k in kws):
            brief.event_type = etype
            break
    for style, kws in _STYLES.items():
        if any(k in lowered for k in kws):
            brief.service_style = style
            break
    if brief.service_style is None and "dinner" in lowered:
        brief.service_style = "plated" if "seated" in lowered else "buffet"

    if "cocktail" in lowered and brief.service_style != "cocktail":
        brief.cocktail_hour = True

    if any(k in lowered for k in ("full bar", "open bar", "liquor", "cocktails at the bar")):
        brief.bar_package = "full_bar"
    elif any(k in lowered for k in ("beer and wine", "beer & wine", "wine and beer")):
        brief.bar_package = "beer_wine"
    elif any(k in lowered for k in ("no alcohol", "dry event", "non-alcoholic")):
        brief.bar_package = "non_alcoholic"

    for pref in ("vegetarian", "vegan", "gluten-free", "salmon", "short rib", "seafood", "chicken"):
        if pref in lowered:
            brief.menu_preferences.append(pref)

    m = re.search(r"(\d+)\s*(?:kids|children|child)", lowered)
    if m:
        brief.child_meals = int(m.group(1))
    m = re.search(r"(\d+)\s*vendor", lowered)
    if m:
        brief.vendor_meals = int(m.group(1))
    return brief


# --------------------------------------------------------------------------- Claude
def _parse_with_claude(text: str, client_name: str | None) -> EventBrief:
    import anthropic

    from .catalog import load_catalog

    venue_ids = list(load_catalog()["venues"].keys())
    tool = {
        "name": "record_event_brief",
        "description": "Record the structured event brief extracted from the salesperson's notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string"},
                "event_date": {"type": "string", "description": "YYYY-MM-DD if a full date is given, else omit"},
                "event_month": {"type": "integer", "minimum": 1, "maximum": 12},
                "venue_id": {"type": "string", "enum": venue_ids},
                "guest_count": {"type": "integer"},
                "event_type": {"type": "string", "enum": ["wedding", "corporate", "social", "gala"]},
                "service_style": {"type": "string", "enum": ["plated", "buffet", "stations", "cocktail"]},
                "cocktail_hour": {"type": "boolean"},
                "bar_package": {"type": "string", "enum": ["beer_wine", "full_bar", "non_alcoholic", "none"]},
                "menu_preferences": {"type": "array", "items": {"type": "string"}},
                "child_meals": {"type": "integer"},
                "vendor_meals": {"type": "integer"},
                "notes": {"type": "string", "description": "Anything else the proposal team should know"},
            },
            "required": ["guest_count"],
        },
    }
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
        max_tokens=1024,
        tools=[tool],
        tool_choice={"type": "tool", "name": "record_event_brief"},
        messages=[{
            "role": "user",
            "content": (
                "Extract the event brief from these sales notes. Only use venue_id values from the enum; "
                f"if the venue is not one of ours, omit it.\n\nNotes:\n{text}"
            ),
        }],
    )
    payload = next(b.input for b in msg.content if b.type == "tool_use")
    payload["raw_text"] = text
    if client_name:
        payload["client_name"] = client_name
    if payload.get("event_date"):
        payload["event_month"] = payload.get("event_month") or int(payload["event_date"][5:7])
    return EventBrief.model_validate(payload)
