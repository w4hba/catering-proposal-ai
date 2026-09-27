from pathlib import Path

from fastapi.testclient import TestClient

from app.docx_writer import write_docx
from app.generator import generate_proposal
from app.main import app

POSTING_BRIEF = ("The client is planning a 150-person wedding at the Brazilian Room in September "
                 "and would like a cocktail reception followed by a seated dinner. Beer and wine bar, "
                 "6 kids and 4 vendor meals.")


def test_pipeline_posting_example():
    draft = generate_proposal(POSTING_BRIEF, client_name="Rivera Family")
    assert draft.venue_name == "The Brazilian Room"
    assert "fall-harvest-plated" in draft.menu_ids
    assert "cocktail-reception-classic" in draft.menu_ids
    assert draft.pricing.total > 0
    assert draft.sources, "retrieval must surface supporting documents"
    assert {"overview", "venue", "menu", "terms"} <= set(draft.narrative)
    # accuracy guarantee: all prices trace to catalog rules
    assert all(i.rule for i in draft.pricing.line_items)


def test_retrieval_surfaces_venue_doc():
    draft = generate_proposal(POSTING_BRIEF)
    assert any("brazilian" in s.doc_id for s in draft.sources)


def test_docx_rendering(tmp_path: Path):
    draft = generate_proposal(POSTING_BRIEF, client_name="Rivera Family")
    out = write_docx(draft, tmp_path / "proposal.docx")
    assert out.exists() and out.stat().st_size > 10_000


def test_api_generate_review_approve(tmp_path):
    client = TestClient(app)
    res = client.post("/api/generate", json={"brief": POSTING_BRIEF, "client_name": "Rivera Family"})
    assert res.status_code == 200, res.text
    draft = res.json()
    assert draft["status"] == "draft"

    res = client.post(f"/api/proposals/{draft['id']}/decision", json={"status": "approved"})
    assert res.json()["status"] == "approved"

    res = client.get(f"/api/proposals/{draft['id']}/docx")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_api_unknown_venue_is_422_not_hallucination():
    client = TestClient(app)
    res = client.post("/api/generate", json={"brief": "300-person wedding at the Grand Palace in June"})
    assert res.status_code == 422
    assert "Known venues" in res.json()["detail"]
