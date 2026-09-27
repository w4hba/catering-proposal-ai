# Catering Proposal AI — Prototype

AI-assisted sales proposal system for a Bay Area catering & events company.
A salesperson types an event brief; the system parses it, retrieves the right
venue and menu documents, applies deterministic pricing rules, and produces a
draft proposal (web preview + .docx) for human review and approval.

Built as the proof of concept scoped in the client posting: **3 venues,
5 menus, published pricing rules, 10 completed proposals**.

## Design principles

1. **No guessed numbers.** Every dollar figure comes from `data/catalog.json`
   through the rules engine (`app/rules.py`); each line item carries a `rule`
   field naming the catalog rule that produced it, so pricing is auditable.
2. **Grounded retrieval.** BM25 retrieval (`app/retrieval.py`) over the
   venue/menu/completed-proposal library supplies the only context the LLM
   sees. The retrieval interface is the swap point for a production vector
   store fed from SharePoint/OneDrive.
3. **Human in the loop.** Every proposal is a `draft` until a salesperson
   approves or sends it back in the review UI. Business-rule violations
   (guest minimums, capacity, missing COI) surface as warnings, never as
   silent auto-corrections.
4. **Degrades gracefully.** With `ANTHROPIC_API_KEY` set, Claude handles
   brief parsing (tool-use structured extraction, venue enum locked to the
   catalog) and narrative writing. Without a key, deterministic regex parsing
   and template narrative keep the full pipeline working — tests are hermetic.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.generate_sample_proposals   # builds the 10-proposal corpus
.venv/bin/python -m pytest                              # 20+ tests
.venv/bin/python -m app.demo --docx                     # CLI demo with the posting's example brief
.venv/bin/uvicorn app.main:app --port 8010              # review UI at http://localhost:8010
```

## Pipeline

```
brief text ──► brief_parser (Claude tool-use │ regex fallback) ──► EventBrief
EventBrief ──► catalog.select_menus (season/type/style filters) ──► menu ids
EventBrief ──► retrieval.DocumentIndex (BM25 over data/) ──► sources
EventBrief + menus ──► rules.price_event (catalog.json only) ──► PricingSummary
all of it  ──► generator (grounded narrative) ──► ProposalDraft ──► review UI / .docx
```

## Repo map

- `data/catalog.json` — venues, menus, pricing rules: the approved source of truth
- `data/venues/`, `data/menus/`, `data/proposals/` — retrieval corpus (Markdown)
- `app/rules.py` — deterministic pricing engine (service charge, county tax,
  staffing ratios, venue fees, Saturday premium, volume discount, minimums)
- `app/brief_parser.py` — Claude structured extraction + offline fallback
- `app/retrieval.py` — pure-Python BM25 index
- `app/generator.py` — draft assembly + grounded narrative
- `app/docx_writer.py` — client-ready Word output
- `app/main.py` + `app/templates/index.html` — FastAPI review/approval UI
- `tests/` — rules, parser, and end-to-end API tests

## Production path (post-prototype)

- Ingestion job: Microsoft Graph API pulls Word/Excel from SharePoint/OneDrive,
  chunks + embeds into a vector store (replacing the BM25 module 1:1).
- Pricing catalog compiled from the company's Excel pricing sheets (openpyxl),
  with a review diff so pricing changes are approved before going live.
- Proposals rendered into the company's own branded Word templates via
  docxtpl; delivery back to SharePoint + optional Power Automate approval flow.
- Eval harness: replay historical briefs against their signed proposals and
  score menu selection + pricing accuracy on every change.
