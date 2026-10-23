import io
import pytest
from fastapi.testclient import TestClient
from docx import Document

from app.main import app
from app.config import settings

client = TestClient(app)

def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["embed_dim"] == 768

def test_api_auth_login():
    # Bad password
    bad_res = client.post("/api/auth/login", json={"password": "wrong-password"})
    assert bad_res.status_code == 401

    # Good password
    good_res = client.post("/api/auth/login", json={"password": settings.APP_PASSWORD})
    assert good_res.status_code == 200
    token_data = good_res.json()
    assert token_data["authenticated"] is True
    assert "token" in token_data

def test_api_chapters_and_citations():
    res = client.get("/api/chapters")
    assert res.status_code == 200
    chapters = res.json()
    assert len(chapters) >= 3
    ch_nums = [c["chapter_no"] for c in chapters]
    assert 1 in ch_nums
    assert 5 in ch_nums
    assert 11 in ch_nums

    # Test chunk citation
    # Find chunk id from first chapter
    c_res = client.get("/api/chunks/490")
    if c_res.status_code == 200:
        chunk = c_res.json()
        assert "citation" in chunk
        assert "text" in chunk

def test_api_blueprints():
    res = client.get("/api/blueprints")
    assert res.status_code == 200
    bps = res.json()
    assert len(bps) >= 2
    titles = [b.get("title", "") for b in bps]
    assert any("Unit Test" in t for t in titles)

def test_api_papers_history_and_detail():
    # List papers
    res = client.get("/api/papers")
    assert res.status_code == 200
    papers = res.json()
    assert len(papers) >= 1
    p1 = papers[0]
    p_id = p1["id"]

    # Detail
    det_res = client.get(f"/api/papers/{p_id}")
    assert det_res.status_code == 200
    det = det_res.json()
    assert det["id"] == p_id
    assert len(det["questions"]) > 0
    assert det["blueprint_report"] is not None

def test_api_question_patch_and_finalize():
    # Fetch paper 1
    det_res = client.get("/api/papers/1")
    if det_res.status_code == 200:
        det = det_res.json()
        q1 = det["questions"][0]
        qid = q1["id"]

        # Accept question
        patch_res = client.patch(f"/api/papers/1/questions/{qid}", json={"status": "accepted"})
        assert patch_res.status_code == 200

        # Finalize paper
        fin_res = client.post("/api/papers/1/finalize")
        assert fin_res.status_code == 200
        fin_data = fin_res.json()
        assert fin_data["saved_to_bank_count"] >= 1

        # Check bank
        bank_res = client.get("/api/bank")
        assert bank_res.status_code == 200
        bank_items = bank_res.json()
        assert len(bank_items) >= 1

def test_api_export_docx():
    # Export question paper
    res_paper = client.get("/api/papers/1/export?part=paper")
    assert res_paper.status_code == 200
    assert res_paper.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    # Verify DOCX zip header
    assert res_paper.content[:4] == b"PK\x03\x04"

    # Export answer key
    res_key = client.get("/api/papers/1/export?part=key")
    assert res_key.status_code == 200
    assert res_key.content[:4] == b"PK\x03\x04"
