"""Pydantic models shared across the pipeline."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

ServiceStyle = Literal["plated", "buffet", "stations", "cocktail"]
EventType = Literal["wedding", "corporate", "social", "gala"]


class EventBrief(BaseModel):
    """Structured event requirements extracted from a salesperson's brief."""

    client_name: str = "TBD"
    event_date: Optional[date] = None
    event_month: Optional[int] = Field(None, ge=1, le=12)
    venue_id: Optional[str] = None
    guest_count: Optional[int] = Field(None, ge=1)
    event_type: Optional[EventType] = None
    service_style: Optional[ServiceStyle] = None
    cocktail_hour: bool = False
    bar_package: Optional[Literal["beer_wine", "full_bar", "non_alcoholic", "none"]] = None
    menu_preferences: list[str] = Field(default_factory=list)
    child_meals: int = 0
    vendor_meals: int = 0
    notes: str = ""
    raw_text: str = ""


class LineItem(BaseModel):
    category: str  # food, bar, staffing, rentals, fees, adjustments
    description: str
    qty: float
    unit: str
    unit_price: float
    amount: float
    rule: str  # which business rule produced this line — auditability


class PricingSummary(BaseModel):
    line_items: list[LineItem]
    food_beverage_subtotal: float
    service_charge: float
    taxable_subtotal: float
    sales_tax: float
    tax_rate: float
    total: float
    deposit_due: float
    per_person: float
    warnings: list[str] = Field(default_factory=list)


class RetrievedSource(BaseModel):
    doc_id: str
    title: str
    score: float
    excerpt: str


class ProposalDraft(BaseModel):
    id: str
    status: Literal["draft", "approved", "rejected"] = "draft"
    brief: EventBrief
    venue_name: str
    menu_ids: list[str]
    menu_names: list[str]
    pricing: PricingSummary
    narrative: dict[str, str]  # section name -> text
    sources: list[RetrievedSource]
    generated_by: Literal["claude", "rules-only"]
    created_at: str
