"""
conftest.py — Fixtures partagées pour les tests d'ingestion.
Importées automatiquement par pytest dans tous les fichiers de test.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.database import Document, IngestionStatus


@pytest.fixture
def sample_doc():
    """Document PostgreSQL minimal pour les tests de pipeline."""
    return Document(
        id=uuid.uuid4(),
        filename="rapport-q1.pdf",
        source_type="pdf",
        collection="finance",
        status=IngestionStatus.PENDING,
        file_size_bytes=102_400,
    )


@pytest.fixture
def mock_qdrant():
    """AsyncMock Qdrant avec les méthodes les plus utilisées préconfigurées."""
    mock = AsyncMock()
    mock.get_collections.return_value = AsyncMock(collections=[])
    mock.upsert.return_value = None
    mock.search.return_value = []
    return mock


@pytest.fixture
def mock_session():
    """AsyncMock SQLAlchemy session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.add    = AsyncMock()
    return session


@pytest.fixture
def tmp_txt_file(tmp_path):
    """Fichier TXT temporaire réaliste pour les tests de loader."""
    content = (
        "# Rapport Q1 2026\n\n"
        "Le chiffre d'affaires du premier trimestre s'élève à 4,2 M€.\n\n"
        "## Points clés\n\n"
        "- Croissance de 18% par rapport à Q1 2025\n"
        "- Segment cloud : 62% des revenus\n"
        "- EBITDA : 19% de marge\n\n"
        "## Perspectives\n\n"
        "Objectif Q2 : 4,8 M€ avec focus sur l'expansion internationale.\n"
    )
    f = tmp_path / "rapport.txt"
    f.write_text(content, encoding="utf-8")
    return str(f)


@pytest.fixture
def tmp_md_file(tmp_path):
    """Fichier Markdown temporaire."""
    content = (
        "# Architecture RAG\n\n"
        "Le pipeline RAG se compose de trois étapes principales :\n\n"
        "1. **Retrieve** : recherche vectorielle dans Qdrant\n"
        "2. **Augment** : construction du prompt avec le contexte\n"
        "3. **Generate** : génération de la réponse via Ollama\n\n"
        "```python\nresult = await pipeline.query(question)\n```\n"
    )
    f = tmp_path / "architecture.md"
    f.write_text(content, encoding="utf-8")
    return str(f)
