"""Render a ProposalDraft to a client-ready .docx via python-docx."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from .catalog import load_catalog
from .models import ProposalDraft

ACCENT = RGBColor(0x8B, 0x5E, 0x34)  # warm brown
GREY = RGBColor(0x55, 0x55, 0x55)


def write_docx(draft: ProposalDraft, out_path: Path) -> Path:
    company = load_catalog()["company"]
    doc = Document()
    for section in doc.sections:
        section.left_margin = section.right_margin = Inches(0.9)

    # Cover
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(company["name"])
    run.font.size, run.font.color.rgb, run.bold = Pt(26), ACCENT, True
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run(f"Catering Proposal for {draft.brief.client_name}")
    r.font.size = Pt(15)
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    when = draft.brief.event_date.strftime("%B %d, %Y") if draft.brief.event_date else (
        f"Month of {draft.brief.event_month}" if draft.brief.event_month else "Date TBD")
    r = meta.add_run(f"{draft.venue_name}  ·  {when}  ·  {draft.brief.guest_count} guests")
    r.font.size, r.font.color.rgb = Pt(11), GREY

    _heading(doc, "Event Overview")
    _md_paragraphs(doc, draft.narrative.get("overview", ""))

    _heading(doc, "Your Venue")
    _md_paragraphs(doc, draft.narrative.get("venue", ""))

    _heading(doc, "Proposed Menu")
    _md_paragraphs(doc, draft.narrative.get("menu", ""))

    _heading(doc, "Investment Summary")
    p = draft.pricing
    table = doc.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, h in enumerate(("Item", "Qty", "Unit", "Amount")):
        hdr[i].paragraphs[0].add_run(h).bold = True
    for item in p.line_items:
        row = table.add_row().cells
        row[0].text = item.description
        row[1].text = f"{item.qty:g}"
        row[2].text = f"${item.unit_price:,.2f}/{item.unit}"
        row[3].text = f"${item.amount:,.2f}"
    for label, amount in (
        ("Service charge (22% of food & beverage)", p.service_charge),
        (f"Sales tax ({p.tax_rate:.3%})", p.sales_tax),
        ("Estimated total", p.total),
        ("Deposit to reserve date", p.deposit_due),
    ):
        row = table.add_row().cells
        row[0].merge(row[2]).paragraphs[0].add_run(label).bold = True
        row[3].paragraphs[0].add_run(f"${amount:,.2f}").bold = True
    pp = doc.add_paragraph()
    r = pp.add_run(f"Approximately ${p.per_person:,.2f} per guest, all-inclusive.")
    r.italic, r.font.color.rgb = True, GREY

    if p.warnings:
        _heading(doc, "For Internal Review")
        for w in p.warnings:
            doc.add_paragraph(w, style="List Bullet")

    _heading(doc, "Terms")
    _md_paragraphs(doc, draft.narrative.get("terms", ""))

    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run(f"{company['name']} · {company['phone']} · {company['email']}")
    r.font.size, r.font.color.rgb = Pt(9), GREY

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path


def _heading(doc, text: str) -> None:
    h = doc.add_heading(text, level=1)
    for run in h.runs:
        run.font.color.rgb = ACCENT


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _md_paragraphs(doc, text: str) -> None:
    """Minimal markdown: #-headings become bold lines, - bullets become list items."""
    for block in text.split("\n"):
        line = block.rstrip()
        if not line.strip():
            continue
        if line.startswith("#"):
            p = doc.add_paragraph()
            p.add_run(line.lstrip("# ").strip()).bold = True
        elif line.lstrip().startswith(("- ", "* ")):
            _runs(doc.add_paragraph(style="List Bullet"), line.lstrip()[2:])
        else:
            _runs(doc.add_paragraph(), line)


def _runs(p, text: str) -> None:
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            p.add_run(text[pos:m.start()])
        p.add_run(m.group(1)).bold = True
        pos = m.end()
    if pos < len(text):
        p.add_run(text[pos:])
