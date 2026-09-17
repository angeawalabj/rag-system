"""
conftest.py — Fixtures partagées pour les tests du RAG API.
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest


@dataclass
class FakeChunk:
    """RetrievedChunk sans dépendance qdrant-client."""
    chunk_id:    str
    text:        str
    score:       float
    source:      str
    source_type: str
    page:        int | None
    collection:  str
    doc_id:      str


@pytest.fixture
def chunk_finance():
    return FakeChunk(
        chunk_id="c-finance-1",
        text="Le CA Q1 2026 est de 4,2 M€, en hausse de 18% vs Q1 2025.",
        score=0.92,
        source="rapport-q1-2026.pdf",
        source_type="pdf",
        page=5,
        collection="finance",
        doc_id="d-001",
    )


@pytest.fixture
def chunk_tech():
    return FakeChunk(
        chunk_id="c-tech-1",
        text="Le pipeline RAG utilise nomic-embed-text pour l'embedding et llama3.2 pour la génération.",
        score=0.87,
        source="architecture.md",
        source_type="md",
        page=None,
        collection="tech",
        doc_id="d-002",
    )


@pytest.fixture
def chunks_multi(chunk_finance, chunk_tech):
    """Liste de plusieurs chunks pour les tests multi-sources."""
    return [chunk_finance, chunk_tech]


@pytest.fixture
def mock_redis():
    """AsyncMock Redis pour le cache."""
    redis = AsyncMock()
    redis.get       = AsyncMock(return_value=None)
    redis.setex     = AsyncMock()
    redis.sadd      = AsyncMock()
    redis.smembers  = AsyncMock(return_value=set())
    redis.delete    = AsyncMock()
    redis.ping      = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_qdrant():
    """AsyncMock Qdrant client."""
    qdrant = AsyncMock()
    qdrant.search          = AsyncMock(return_value=[])
    qdrant.get_collections = AsyncMock(return_value=AsyncMock(collections=[]))
    return qdrant
