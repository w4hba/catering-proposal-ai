"""FastAPI app: event brief in → draft proposal out → human review/approval."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .catalog import load_catalog
from .docx_writer import write_docx
from .generator import generate_proposal
from .models import ProposalDraft

app = FastAPI(title="Catering Proposal AI")

OUT_DIR = Path(__file__).resolve().parent.parent / "out"
TEMPLATES = Path(__file__).resolve().parent / "templates"

_drafts: dict[str, ProposalDraft] = {}


class GenerateRequest(BaseModel):
    brief: str
    client_name: str | None = None


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (TEMPLATES / "index.html").read_text()


@app.get("/api/catalog")
def catalog_summary() -> dict:
    c = load_catalog()
    return {
        "company": c["company"]["name"],
        "venues": [{"id": k, "name": v["name"], "location": v["location"]} for k, v in c["venues"].items()],
        "menus": [{"id": k, "name": m["name"], "price_per_person": m["price_per_person"]} for k, m in c["menus"].items()],
    }


@app.post("/api/generate")
def generate(req: GenerateRequest) -> ProposalDraft:
    try:
        draft = generate_proposal(req.brief, req.client_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _drafts[draft.id] = draft
    _persist(draft)
    return draft


@app.get("/api/proposals/{draft_id}")
def get_draft(draft_id: str) -> ProposalDraft:
    return _get(draft_id)


@app.post("/api/proposals/{draft_id}/decision")
def decide(draft_id: str, decision: dict) -> ProposalDraft:
    draft = _get(draft_id)
    status = decision.get("status")
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    draft.status = status
    _persist(draft)
    return draft


@app.get("/api/proposals/{draft_id}/docx")
def download_docx(draft_id: str) -> FileResponse:
    draft = _get(draft_id)
    path = OUT_DIR / f"proposal_{draft_id}.docx"
    write_docx(draft, path)
    safe_client = "".join(ch for ch in draft.brief.client_name if ch.isalnum() or ch in " -_").strip() or "client"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"Proposal - {safe_client}.docx",
    )


def _get(draft_id: str) -> ProposalDraft:
    if draft_id in _drafts:
        return _drafts[draft_id]
    path = OUT_DIR / f"proposal_{draft_id}.json"
    if path.exists():
        draft = ProposalDraft.model_validate_json(path.read_text())
        _drafts[draft_id] = draft
        return draft
    raise HTTPException(status_code=404, detail="Draft not found")


def _persist(draft: ProposalDraft) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"proposal_{draft.id}.json").write_text(json.dumps(draft.model_dump(mode="json"), indent=2))
