"""Deterministic pricing engine.

Every line item cites the catalog rule that produced it. The LLM never
touches this module's output — pricing is pure arithmetic over catalog.json,
which is the requirement the client posting calls out ("We do not want an AI
system that guesses pricing").
"""
from __future__ import annotations

import math

from .catalog import load_catalog, menu, pricing_rules, venue
from .models import EventBrief, LineItem, PricingSummary


def _li(category: str, description: str, qty: float, unit: str, unit_price: float, rule: str) -> LineItem:
    return LineItem(
        category=category,
        description=description,
        qty=qty,
        unit=unit,
        unit_price=unit_price,
        amount=round(qty * unit_price, 2),
        rule=rule,
    )


def price_event(brief: EventBrief, menu_ids: list[str]) -> PricingSummary:
    rules = pricing_rules()
    v = venue(brief.venue_id)
    guests = brief.guest_count or 0
    style = brief.service_style or "buffet"
    warnings: list[str] = []
    items: list[LineItem] = []

    if guests < v["guest_minimum"]:
        warnings.append(
            f"Guest count {guests} is below {v['name']}'s minimum of {v['guest_minimum']}; "
            f"pricing assumes the {v['guest_minimum']}-guest minimum."
        )
        guests = v["guest_minimum"]
    cap = v["capacity_standing"] if style == "cocktail" else v["capacity_seated"]
    if guests > cap:
        warnings.append(
            f"Guest count {guests} exceeds {v['name']}'s capacity of {cap} for {style} service — flag for review."
        )

    adult_guests = max(guests - brief.child_meals, 0)

    # --- Food ---
    for mid in menu_ids:
        m = menu(mid)
        is_addon = (
            mid == rules["cocktail_hour_addon"]["menu_id"]
            and brief.service_style != "cocktail"
            and len(menu_ids) > 1
        )
        pp = m["addon_only_with_dinner_price_per_person"] if is_addon else m["price_per_person"]
        label = f"{m['name']}" + (" (cocktail hour add-on)" if is_addon else "")
        items.append(_li("food", label, adult_guests, "guest", pp, f"menus.{mid}"))

    if brief.child_meals:
        items.append(_li("food", "Children's meals", brief.child_meals, "meal",
                         rules["special_meals"]["child_meal_price"], "special_meals.child_meal_price"))
    if brief.vendor_meals:
        items.append(_li("food", "Vendor meals", brief.vendor_meals, "meal",
                         rules["special_meals"]["vendor_meal_price"], "special_meals.vendor_meal_price"))

    # --- Bar ---
    bar_map = {
        "beer_wine": ("Beer & wine package", rules["bar"]["beer_wine_package_per_person"], "bar.beer_wine_package_per_person"),
        "full_bar": ("Full bar package", rules["bar"]["full_bar_package_per_person"], "bar.full_bar_package_per_person"),
        "non_alcoholic": ("Non-alcoholic beverage package", rules["bar"]["non_alcoholic_per_person"], "bar.non_alcoholic_per_person"),
    }
    if brief.bar_package in bar_map:
        label, pp, rule = bar_map[brief.bar_package]
        items.append(_li("bar", label, adult_guests, "guest", pp, rule))

    # --- Surcharges tied to venue/style ---
    if style == "plated" and v.get("kitchen_fee") and "warming" in v.get("notes_for_pricing", "").lower():
        items.append(_li("food", f"Warming-kitchen plated surcharge ({v['name']})", adult_guests, "guest",
                         rules["surcharges"]["warming_kitchen_plated_per_person"],
                         "surcharges.warming_kitchen_plated_per_person"))

    # --- Staffing ---
    staff = rules["staffing"]
    hours = staff["minimum_hours"]
    servers = math.ceil(guests / staff["guests_per_server"][style])
    items.append(_li("staffing", f"Servers ({servers} x {hours} hrs)", servers * hours, "hr",
                     staff["server_hourly"], f"staffing.guests_per_server.{style}"))
    chefs = staff["chefs_per_event"][style]
    items.append(_li("staffing", f"Chefs ({chefs} x {hours} hrs)", chefs * hours, "hr",
                     staff["chef_hourly"], f"staffing.chefs_per_event.{style}"))
    items.append(_li("staffing", f"Event captain (1 x {hours} hrs)", staff["captains_per_event"] * hours, "hr",
                     staff["captain_hourly"], "staffing.captains_per_event"))
    if brief.bar_package in ("beer_wine", "full_bar"):
        bartenders = max(1, math.ceil(guests / staff["guests_per_bartender"]))
        items.append(_li("staffing", f"Bartenders ({bartenders} x {hours} hrs)", bartenders * hours, "hr",
                         staff["bartender_hourly"], "staffing.guests_per_bartender"))

    # --- Rentals & fees ---
    items.append(_li("rentals", f"Rentals estimate — {style} service", guests, "guest",
                     rules["rentals_per_person"][style], f"rentals_per_person.{style}"))
    items.append(_li("fees", f"Kitchen fee — {v['name']}", 1, "flat", v["kitchen_fee"], f"venues.{brief.venue_id}.kitchen_fee"))
    items.append(_li("fees", "Delivery & logistics", 1, "flat",
                     rules["delivery_fee_by_zone"][v["delivery_zone"]],
                     f"delivery_fee_by_zone.{v['delivery_zone']}"))

    # --- Adjustments ---
    fb_subtotal = sum(i.amount for i in items if i.category in ("food", "bar"))
    if brief.event_date is not None and brief.event_date.weekday() == 5:
        pct = rules["surcharges"]["saturday_premium_pct"]
        items.append(_li("adjustments", f"Saturday premium ({pct:.0%} of food & beverage)", 1, "flat",
                         round(fb_subtotal * pct, 2), "surcharges.saturday_premium_pct"))
    disc = rules["surcharges"]["guest_count_discount"]
    if guests >= disc["threshold"]:
        items.append(_li("adjustments", f"Large-event discount ({disc['pct']:.0%} of food & beverage)", 1, "flat",
                         -round(fb_subtotal * disc["pct"], 2), "surcharges.guest_count_discount"))

    # --- Totals ---
    fb_total = sum(i.amount for i in items if i.category in ("food", "bar", "adjustments"))
    service_charge = round(fb_total * rules["service_charge_pct"], 2)
    tax_rate = rules["sales_tax_by_county"][v["county"]]
    taxable = round(fb_total + service_charge + sum(i.amount for i in items if i.category == "rentals"), 2)
    sales_tax = round(taxable * tax_rate, 2)
    total = round(sum(i.amount for i in items) + service_charge + sales_tax, 2)
    deposit = round(total * load_catalog()["company"]["deposit_pct"], 2)

    if v.get("insurance_required"):
        warnings.append(f"{v['name']} requires a certificate of insurance — confirm COI on file before event.")

    return PricingSummary(
        line_items=items,
        food_beverage_subtotal=round(fb_total, 2),
        service_charge=service_charge,
        taxable_subtotal=taxable,
        sales_tax=sales_tax,
        tax_rate=tax_rate,
        total=total,
        deposit_due=deposit,
        per_person=round(total / guests, 2) if guests else 0.0,
        warnings=warnings,
    )
