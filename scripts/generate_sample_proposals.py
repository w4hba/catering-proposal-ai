"""Generate the 10 'completed proposals' sample dataset by running the pipeline
over historical event briefs, then saving each as a markdown doc that joins
the retrieval corpus (mirrors the client's real completed-proposal library).

Run once: python -m scripts.generate_sample_proposals
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.generator import generate_proposal  # noqa: E402

HISTORICAL_BRIEFS = [
    ("Nguyen-Okafor Wedding", "Client is Nguyen-Okafor. 140-person wedding at the Brazilian Room on 2025-09-13, cocktail reception then seated dinner, beer and wine, 4 kids."),
    ("Alvarez 50th Anniversary", "Client is The Alvarez Family. 90-person anniversary seated dinner at Piedmont Community Hall in October, plated, beer and wine."),
    ("Meridian Fund Gala", "Client name is Meridian Fund. 180 guest gala at the General's Residence in October, cocktail-style standing reception, full bar."),
    ("Brightline Offsite", "Client is Brightline Robotics. Corporate offsite lunch for 75 people at Piedmont Community Hall in May, buffet, no alcohol."),
    ("Kaplan-Reyes Wedding", "Client is Kaplan-Reyes. 120-person wedding at the General's Residence on 2025-10-04, seated fall dinner with cocktail hour, full bar, 5 vendor meals."),
    ("Sona Biotech Client Dinner", "Client is Sona Biotech. 60-person client dinner at Piedmont Community Hall in November, plated, beer and wine."),
    ("Harper Birthday", "Client is Dana Harper. 110-person birthday party at the Brazilian Room in June, buffet with cocktail hour, full bar, 8 kids."),
    ("Westfield School Benefit", "Client is Westfield School. 160-person fundraiser gala at the Brazilian Room in April, buffet dinner with cocktail reception, beer and wine."),
    ("Ito-Marsh Wedding", "Client is Ito-Marsh. 100-person wedding at Piedmont Community Hall on 2025-07-19, seated summer dinner with cocktail hour, beer and wine, 3 kids, 4 vendors."),
    ("Golden Hills HOA Summer Social", "Client is Golden Hills HOA. 200-person summer social at Piedmont Community Hall in August, cocktail-style reception, non-alcoholic."),
]

OUT = Path(__file__).resolve().parent.parent / "data" / "proposals"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for slug_title, brief_text in HISTORICAL_BRIEFS:
        draft = generate_proposal(brief_text)
        slug = slug_title.lower().replace(" ", "_").replace("-", "_")
        b, p = draft.brief, draft.pricing
        lines = [
            f"# Completed Proposal — {slug_title}",
            "",
            f"**Venue:** {draft.venue_name}  ",
            f"**Guests:** {b.guest_count}  ",
            f"**Event type:** {b.event_type} · {b.service_style}" + (" + cocktail hour" if b.cocktail_hour else "") + "  ",
            f"**Menus:** {', '.join(draft.menu_names)}  ",
            f"**Final total:** ${p.total:,.2f} (${p.per_person:,.2f}/guest)",
            "",
            "## Overview",
            draft.narrative["overview"],
            "",
            "## Line Items",
        ]
        lines += [f"- {i.description}: ${i.amount:,.2f}" for i in p.line_items]
        lines += ["", "## Outcome", "Proposal approved by sales and signed by client. Event executed as planned."]
        (OUT / f"{slug}.md").write_text("\n".join(lines))
        print(f"wrote {slug}.md  (total ${p.total:,.2f})")


if __name__ == "__main__":
    main()
