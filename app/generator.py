"""Assemble a ProposalDraft: retrieve sources, pick menus, price, write narrative.

Narrative text is the only place the LLM writes prose, and it is grounded in
retrieved venue/menu docs passed as context. With no API key, template-based
narrative keeps the pipeline fully functional.
"""
from __future__ import annotations

import calendar
import os
import uuid
from datetime import datetime, timezone

from . import catalog
from .brief_parser import parse_brief
from .models import EventBrief, ProposalDraft, RetrievedSource
from .retrieval import DocumentIndex
from .rules import price_event

_index: DocumentIndex | None = None


def get_index() -> DocumentIndex:
    global _index
    if _index is None:
        _index = DocumentIndex.build()
    return _index


def generate_proposal(text: str, client_name: str | None = None) -> ProposalDraft:
    brief, parser_used = parse_brief(text, client_name)
    return generate_from_brief(brief, parser_used)


def generate_from_brief(brief: EventBrief, parser_used: str = "rules-only") -> ProposalDraft:
    if not brief.venue_id:
        raise ValueError(
            "Could not match a venue in the brief. Known venues: "
            + ", ".join(v["name"] for v in catalog.load_catalog()["venues"].values())
        )
    if not brief.guest_count:
        raise ValueError("Guest count is required to price a proposal.")

    menu_ids = catalog.select_menus(
        brief.event_month, brief.event_type, brief.service_style, brief.cocktail_hour, brief.menu_preferences
    )
    if not menu_ids:
        raise ValueError(
            f"No approved menu matches month={brief.event_month}, type={brief.event_type}, "
            f"style={brief.service_style}. A salesperson must choose manually."
        )

    v = catalog.venue(brief.venue_id)
    query = " ".join(filter(None, [
        v["name"], brief.event_type or "", brief.service_style or "",
        calendar.month_name[brief.event_month] if brief.event_month else "",
        " ".join(brief.menu_preferences),
    ]))
    sources = get_index().search(query, top_k=4)
    # The venue and menu docs ground the narrative, so they are always cited
    # even when completed proposals outrank them in BM25.
    pinned_ids = [v["doc"], *(catalog.menu(m)["doc"] for m in menu_ids)]
    have = {s.doc_id for s in sources}
    for pid in reversed(pinned_ids):
        if pid not in have and (src := get_index().get(pid)):
            sources.insert(0, src)
    pricing = price_event(brief, menu_ids)
    menu_names = [catalog.menu(m)["name"] for m in menu_ids]

    narrative = _write_narrative(brief, v, menu_ids, sources)
    generated_by = "claude" if (parser_used == "claude" or narrative.pop("_llm", None)) else "rules-only"

    return ProposalDraft(
        id=uuid.uuid4().hex[:10],
        brief=brief,
        venue_name=v["name"],
        menu_ids=menu_ids,
        menu_names=menu_names,
        pricing=pricing,
        narrative=narrative,
        sources=sources,
        generated_by=generated_by,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ------------------------------------------------------------------ narrative
def _write_narrative(brief: EventBrief, v: dict, menu_ids: list[str], sources: list[RetrievedSource]) -> dict:
    sections = _template_narrative(brief, v, menu_ids)
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            sections.update(_claude_narrative(brief, v, menu_ids, sources))
            sections["_llm"] = "1"
        except Exception:
            pass
    return sections


def _event_label(brief: EventBrief) -> str:
    style = {"plated": "seated dinner", "buffet": "buffet dinner", "stations": "chef stations",
             "cocktail": "cocktail reception"}.get(brief.service_style or "", "celebration")
    pieces = []
    if brief.cocktail_hour:
        pieces.append("cocktail reception")
    pieces.append(style)
    when = ""
    if brief.event_date:
        when = brief.event_date.strftime(" on %B %-d, %Y")
    elif brief.event_month:
        when = f" in {calendar.month_name[brief.event_month]}"
    return f"{(brief.event_type or 'event').title()} — {' followed by '.join(pieces)}{when}"


def _template_narrative(brief: EventBrief, v: dict, menu_ids: list[str]) -> dict:
    venue_doc = catalog.read_doc(v["doc"])
    logistics = _section_of(venue_doc, "Catering Logistics")
    menus_text = "\n\n".join(catalog.read_doc(catalog.menu(m)["doc"]) for m in menu_ids)
    guests = brief.guest_count or 0
    return {
        "overview": (
            f"Thank you for considering {catalog.load_catalog()['company']['name']} for "
            f"{brief.client_name}'s {_event_label(brief).lower()} at {v['name']} for {guests} guests. "
            f"This proposal reflects our current menus and published pricing; your event manager will "
            f"refine details with you after review."
        ),
        "venue": f"**{v['name']}**, {v['location']}.\n\n{logistics}".strip(),
        "menu": menus_text,
        "terms": (
            f"Prices valid for {catalog.load_catalog()['company']['proposal_valid_days']} days. "
            f"A {catalog.load_catalog()['company']['deposit_pct']:.0%} deposit reserves your date. "
            "Final guest counts and entrée selections are due 14 days before the event. "
            "Service charge and applicable sales tax are itemized in the investment summary."
        ),
    }


def _section_of(doc: str, heading: str) -> str:
    lines, keep, out = doc.splitlines(), False, []
    for line in lines:
        if line.startswith("## "):
            keep = heading.lower() in line.lower()
            continue
        if keep:
            out.append(line)
    return "\n".join(out).strip()


def _claude_narrative(brief: EventBrief, v: dict, menu_ids: list[str], sources: list[RetrievedSource]) -> dict:
    import anthropic

    context = "\n\n---\n\n".join(f"[{s.doc_id}]\n{catalog.read_doc(s.doc_id)}" for s in sources)
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
        max_tokens=1200,
        system=(
            "You write the overview and venue sections of catering proposals. Use ONLY facts present in the "
            "provided documents — never invent prices, menu items, or venue rules. Warm, professional, concise. "
            "Return two paragraphs separated by the line '===VENUE===': first the event overview, then the venue "
            "narrative (setting + the logistics/rules the client should know)."
        ),
        messages=[{"role": "user", "content": f"Event brief:\n{brief.model_dump_json(indent=2)}\n\nDocuments:\n{context}"}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    if "===VENUE===" in text:
        overview, venue_text = text.split("===VENUE===", 1)
        return {"overview": overview.strip(), "venue": venue_text.strip()}
    return {"overview": text.strip()}
