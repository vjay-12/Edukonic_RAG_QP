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

def test_content_type_rules():
    """Verify content type classification rules per specification."""
    from app.services.chunker import determine_content_type

    assert determine_content_type("###### **Activity 1.1**", "Clean a magnesium ribbon...") == "activity"
    assert determine_content_type("Activity 5.2", "Take some yeast...") == "activity"
    assert determine_content_type("###### Example 11.1", "A current of 0.5 A is drawn...") == "example"
    assert determine_content_type("Questions", "1. Why does the cord of an electric heater not glow?") == "exercise"
    assert determine_content_type("Exercises", "1. A piece of wire of resistance R is cut...") == "exercise"
    assert determine_content_type("What you have learnt", "A complete chemical equation represents...") == "summary"
    assert determine_content_type("Summary", "In this chapter we studied electric circuits...") == "summary"
    assert determine_content_type("1.1 Chemical Equations", "When a magnesium ribbon is burnt in oxygen...") == "concept"

def test_chunker_section_boundaries_and_limits():
    """Verify that chunker respects section boundaries and max token limits."""
    from app.services.chunker import chunk_markdown_pages
    from app.config import settings

    # Synthetic multi-section markdown pages
    long_para = "This is a detailed scientific concept explanation with multiple facts and observations. " * 30
    pages_fixture = [
        {
            "metadata": {"page_number": 1},
            "text": f"###### 1.1 Section One\n\n{long_para}\n\n###### **Activity 1.1**\n\nTake zinc granules in a flask and add dilute acid."
        },
        {
            "metadata": {"page_number": 2},
            "text": "###### Questions\n\n1. What happens when zinc reacts with acid?\n2. Name the gas evolved."
        }
    ]

    chunks = chunk_markdown_pages(pages_fixture, chapter_no=1)
    assert len(chunks) >= 3

    # Check that each chunk respects the max token limit
    for c in chunks:
        assert c["token_count"] <= settings.CHUNK_MAX_TOKENS
        assert c["token_count"] >= 10

    # Check that Activity is not combined into Section One concept
    types = [c["content_type"] for c in chunks]
    assert "concept" in types
    assert "activity" in types
    assert "exercise" in types

def test_mock_embedding():
    """Verify embedding function behaves consistently and returns unit-normalized vectors."""
    import math
    from app.services.llm import embed, embed_one

    # Test single
    vec = embed_one("CBSE Class 10 Science Ohm's law")
    assert len(vec) == 768
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3

    # Test batch
    batch_vecs = embed(["Chemical equations", "Life processes"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 768
    assert len(batch_vecs[1]) == 768
