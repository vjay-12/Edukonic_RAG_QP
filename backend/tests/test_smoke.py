import pytest
from fastapi.testclient import TestClient

def test_backend_imports():
    """Verify core application modules can be imported without error."""
    from app.main import app
    from app.config import settings
    from app.db import Base, engine
    from app.models import Document, Chunk, Paper, PaperQuestion, QuestionBank, ReferenceQuestion
    from app.services.llm import embed_one, count_tokens
    from app.services.chunker import clean_page_text, determine_content_type

    assert app is not None
    assert settings.EMBED_DIM == 768
    assert settings.EMBED_PROVIDER == "local"

def test_health_endpoint():
    """Verify GET /api/health returns HTTP 200 with ok status."""
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Edukonic_RAG_QP"
    assert data["embed_dim"] == 768

def test_chunker_unit():
    """Verify chunker text cleaning and content type classification."""
    from app.services.chunker import clean_page_text, determine_content_type
    from app.services.llm import count_tokens

    # Test clean_page_text: hyphen joining and page number removal
    raw_sample = "This is a chemi-\ncal reaction test.\n42\nRationalised 2023-24\nEnd of text."
    cleaned = clean_page_text(raw_sample)
    assert "chemical" in cleaned
    assert "\n42\n" not in cleaned
    assert "Rationalised" not in cleaned

    # Test determine_content_type
    assert determine_content_type("Activity 1.1", "Observe what happens...") == "activity"
    assert determine_content_type("Example 11.1", "A current of 0.5 A...") == "example"
    assert determine_content_type("Questions", "1. Why should a magnesium ribbon...") == "exercise"
    assert determine_content_type("What you have learnt", "A complete chemical equation...") == "summary"
    assert determine_content_type("1.1 Chemical Equations", "When magnesium ribbon burns...") == "concept"

    # Test count_tokens
    cnt = count_tokens("Chemical Reactions and Equations")
    assert cnt > 0

def test_embedding_local():
    """Verify local sentence-transformer embedding returns 768 normalized dimensions."""
    import math
    from app.services.llm import embed_one

    vec = embed_one("CBSE Class 10 Science question test")
    assert len(vec) == 768
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3
