"""CLI demo: python -m app.demo "<event brief>" [--docx]"""
from __future__ import annotations

import sys
from pathlib import Path

from .docx_writer import write_docx
from .generator import generate_proposal

DEFAULT_BRIEF = (
    "The client is planning a 150-person wedding at the Brazilian Room in September "
    "and would like a cocktail reception followed by a seated dinner. Beer and wine bar, "
    "6 kids and 4 vendor meals."
)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--docx"]
    brief_text = args[0] if args else DEFAULT_BRIEF
    draft = generate_proposal(brief_text)

    b, p = draft.brief, draft.pricing
    print(f"\n=== Draft proposal {draft.id} ({draft.generated_by}) ===")
    print(f"Client:  {b.client_name}")
    print(f"Venue:   {draft.venue_name}")
    print(f"Event:   {b.event_type} · {b.service_style}" + (" + cocktail hour" if b.cocktail_hour else ""))
    print(f"Guests:  {b.guest_count} (+{b.child_meals} kids, +{b.vendor_meals} vendors)")
    print(f"Menus:   {', '.join(draft.menu_names)}")
    print(f"\nSources: " + ", ".join(s.doc_id for s in draft.sources))
    print("\n--- Investment summary ---")
    for i in p.line_items:
        print(f"  {i.description:<52} {i.qty:>7g} x ${i.unit_price:>8,.2f}  = ${i.amount:>10,.2f}   [{i.rule}]")
    print(f"  {'Service charge':<52} {'':>22} = ${p.service_charge:>10,.2f}")
    print(f"  {'Sales tax (' + format(p.tax_rate, '.3%') + ')':<52} {'':>22} = ${p.sales_tax:>10,.2f}")
    print(f"  {'TOTAL':<52} {'':>22} = ${p.total:>10,.2f}  (${p.per_person:,.2f}/guest)")
    for w in p.warnings:
        print(f"  ⚠ {w}")

    if "--docx" in sys.argv:
        out = Path(__file__).resolve().parent.parent / "out" / f"proposal_{draft.id}.docx"
        write_docx(draft, out)
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
