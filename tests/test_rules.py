from datetime import date

import pytest

from app.catalog import load_catalog, select_menus
from app.models import EventBrief
from app.rules import price_event


def make_brief(**kw) -> EventBrief:
    base = dict(
        client_name="Test Client", venue_id="brazilian-room", guest_count=150,
        event_type="wedding", service_style="plated", event_month=9,
    )
    base.update(kw)
    return EventBrief(**base)


def test_menu_selection_september_plated_wedding():
    menus = select_menus(9, "wedding", "plated", cocktail_hour=True)
    assert "cocktail-reception-classic" in menus
    # September plated wedding matches both summer coastal and fall harvest; fall is cheaper
    assert menus[0] == "fall-harvest-plated"


def test_menu_preferences_steer_selection():
    menus = select_menus(9, "wedding", "plated", cocktail_hour=False, preferences=["short rib"])
    assert menus == ["fall-harvest-plated"]
    menus = select_menus(9, "wedding", "plated", cocktail_hour=False, preferences=["king salmon", "stone fruit"])
    assert menus == ["summer-coastal-plated"]


def test_every_line_item_cites_a_rule():
    brief = make_brief(bar_package="beer_wine", child_meals=6, vendor_meals=4)
    pricing = price_event(brief, ["fall-harvest-plated", "cocktail-reception-classic"])
    assert all(i.rule for i in pricing.line_items)


def test_totals_are_consistent():
    brief = make_brief(bar_package="beer_wine")
    p = price_event(brief, ["fall-harvest-plated"])
    line_sum = round(sum(i.amount for i in p.line_items), 2)
    assert p.total == round(line_sum + p.service_charge + p.sales_tax, 2)
    assert p.sales_tax == round(p.taxable_subtotal * p.tax_rate, 2)
    assert p.per_person == round(p.total / 150, 2)


def test_cocktail_addon_uses_addon_price():
    brief = make_brief(cocktail_hour=True)
    p = price_event(brief, ["fall-harvest-plated", "cocktail-reception-classic"])
    addon = next(i for i in p.line_items if "add-on" in i.description)
    assert addon.unit_price == load_catalog()["menus"]["cocktail-reception-classic"][
        "addon_only_with_dinner_price_per_person"]


def test_guest_minimum_enforced_with_warning():
    brief = make_brief(guest_count=30, venue_id="brazilian-room", service_style="buffet")
    p = price_event(brief, ["spring-garden-buffet"])
    food = next(i for i in p.line_items if i.rule.startswith("menus."))
    assert food.qty == 50  # Brazilian Room minimum
    assert any("minimum" in w for w in p.warnings)


def test_capacity_overflow_warns():
    brief = make_brief(guest_count=200, service_style="plated")
    p = price_event(brief, ["fall-harvest-plated"])
    assert any("capacity" in w for w in p.warnings)


def test_saturday_premium_applied():
    sat = make_brief(event_date=date(2026, 9, 12))  # a Saturday
    fri = make_brief(event_date=date(2026, 9, 11))
    p_sat = price_event(sat, ["fall-harvest-plated"])
    p_fri = price_event(fri, ["fall-harvest-plated"])
    assert any("Saturday" in i.description for i in p_sat.line_items)
    assert not any("Saturday" in i.description for i in p_fri.line_items)
    assert p_sat.total > p_fri.total


def test_large_event_discount():
    brief = make_brief(guest_count=180, venue_id="piedmont-hall")
    p = price_event(brief, ["fall-harvest-plated"])
    disc = next(i for i in p.line_items if "discount" in i.description.lower())
    assert disc.amount < 0


def test_warming_kitchen_surcharge_only_at_generals_residence():
    gr = make_brief(venue_id="generals-residence", guest_count=120)
    br = make_brief(venue_id="brazilian-room", guest_count=120)
    p_gr = price_event(gr, ["fall-harvest-plated"])
    p_br = price_event(br, ["fall-harvest-plated"])
    assert any("Warming-kitchen" in i.description for i in p_gr.line_items)
    assert not any("Warming-kitchen" in i.description for i in p_br.line_items)


def test_county_tax_rates_differ():
    sf = price_event(make_brief(venue_id="generals-residence", guest_count=120), ["fall-harvest-plated"])
    alameda = price_event(make_brief(venue_id="brazilian-room", guest_count=120), ["fall-harvest-plated"])
    assert sf.tax_rate == pytest.approx(0.08625)
    assert alameda.tax_rate == pytest.approx(0.1025)
