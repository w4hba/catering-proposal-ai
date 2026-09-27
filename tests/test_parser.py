from app.brief_parser import _parse_with_rules


def test_posting_example_brief():
    text = ("The client is planning a 150-person wedding at the Brazilian Room in September "
            "and would like a cocktail reception followed by a seated dinner.")
    b = _parse_with_rules(text, None)
    assert b.guest_count == 150
    assert b.venue_id == "brazilian-room"
    assert b.event_type == "wedding"
    assert b.event_month == 9
    assert b.service_style == "plated"
    assert b.cocktail_hour is True


def test_corporate_iso_date_and_dietary():
    text = ("Corporate offsite lunch for 80 people at Piedmont Community Hall on 2026-04-16, "
            "buffet, no alcohol, several vegetarian guests.")
    b = _parse_with_rules(text, None)
    assert b.guest_count == 80
    assert b.venue_id == "piedmont-hall"
    assert b.event_type == "corporate"
    assert b.event_date and b.event_date.isoformat() == "2026-04-16"
    assert b.service_style == "buffet"
    assert b.bar_package == "non_alcoholic"
    assert "vegetarian" in b.menu_preferences


def test_gala_full_bar_and_client_name():
    text = ("Client is Meridian Fund. 180 guest gala at the General's Residence in October, "
            "cocktail-style standing reception with full bar, 4 vendor meals.")
    b = _parse_with_rules(text, None)
    assert b.client_name == "Meridian Fund"
    assert b.venue_id == "generals-residence"
    assert b.event_type == "gala"
    assert b.service_style == "cocktail"
    assert b.bar_package == "full_bar"
    assert b.vendor_meals == 4


def test_kids_and_beer_wine():
    b = _parse_with_rules("120 guests, wedding at Tilden in July, buffet, beer and wine, 6 kids", None)
    assert b.venue_id == "brazilian-room"  # via 'tilden' alias
    assert b.bar_package == "beer_wine"
    assert b.child_meals == 6


def test_unknown_venue_returns_none():
    b = _parse_with_rules("200-person wedding at the Ritz ballroom in June", None)
    assert b.venue_id is None
