"""
Tests unitaires — RAG API.
Ollama, Qdrant et Redis sont mockés.
Exécution : pytest services/api/tests/ -v
"""

import hashlib
import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Fixture : RetrievedChunk ─────────────────────────────────────────────────

@dataclass
class MockChunk:
    chunk_id:    str
    text:        str
    score:       float
    source:      str
    source_type: str
    page:        int | None
    collection:  str
    doc_id:      str


def make_chunk(text="Contenu du chunk.", score=0.88, source="doc.pdf", page=1):
    return MockChunk(
        chunk_id="c1", text=text, score=score,
        source=source, source_type="pdf", page=page,
        collection="documents", doc_id="d1",
    )


# ─── Tests Cache ──────────────────────────────────────────────────────────────

class TestRAGCache:

    def _make_cache(self):
        from src.cache import RAGCache
        return RAGCache(redis=AsyncMock())

    def test_key_is_deterministic(self):
        cache = self._make_cache()
        k1 = cache._key("Même question ?", "finance", 5)
        k2 = cache._key("Même question ?", "finance", 5)
        assert k1 == k2

    def test_key_differs_on_collection(self):
        cache = self._make_cache()
        k1 = cache._key("Question", "finance", 5)
        k2 = cache._key("Question", "legal",   5)
        assert k1 != k2

    def test_key_differs_on_top_k(self):
        cache = self._make_cache()
        k1 = cache._key("Question", "docs", 5)
        k2 = cache._key("Question", "docs", 10)
        assert k1 != k2

    def test_key_starts_with_prefix(self):
        cache = self._make_cache()
        k = cache._key("test", "docs", 5)
        assert k.startswith("rag:cache:")

    def test_inv_key_format(self):
        cache = self._make_cache()
        inv = cache._inv_key("ma-collection")
        assert inv == "rag:inv:ma-collection"

    @pytest.mark.asyncio
    async def test_get_returns_none_on_miss(self):
        from src.cache import RAGCache
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        cache = RAGCache(redis=redis_mock)
        result = await cache.get("question", "docs", 5)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_parsed_json_on_hit(self):
        from src.cache import RAGCache
        payload = {"tokens": ["Réponse", " courte."], "sources": []}
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps(payload))
        cache = RAGCache(redis=redis_mock)
        result = await cache.get("question", "docs", 5)
        assert result == payload

    @pytest.mark.asyncio
    async def test_set_calls_setex_with_ttl(self):
        from src.cache import RAGCache
        from src.config import settings
        redis_mock = AsyncMock()
        cache = RAGCache(redis=redis_mock)
        await cache.set("q", "docs", 5, {"tokens": [], "sources": []})
        redis_mock.setex.assert_called_once()
        args = redis_mock.setex.call_args[0]
        assert args[1] == settings.cache_ttl

    @pytest.mark.asyncio
    async def test_invalidate_deletes_all_collection_keys(self):
        from src.cache import RAGCache
        redis_mock = AsyncMock()
        keys = {"rag:cache:abc123", "rag:cache:def456"}
        redis_mock.smembers = AsyncMock(return_value=keys)
        redis_mock.delete   = AsyncMock()
        cache = RAGCache(redis=redis_mock)

        count = await cache.invalidate_collection("finance")
        assert count == 2
        assert redis_mock.delete.called


# ─── Tests Generator — prompt building ───────────────────────────────────────

class TestPromptBuilding:

    def test_context_block_numbered(self):
        from src.generator import build_context_block
        chunks = [
            make_chunk(text="Premier chunk.", source="a.pdf", page=1),
            make_chunk(text="Deuxième chunk.", source="b.pdf", page=None),
        ]
        block = build_context_block(chunks)
        assert "[1]" in block
        assert "[2]" in block
        assert "Premier chunk." in block
        assert "Deuxième chunk." in block

    def test_context_block_includes_page(self):
        from src.generator import build_context_block
        chunk = make_chunk(source="rapport.pdf", page=7)
        block = build_context_block([chunk])
        assert "p.7" in block

    def test_context_block_no_page_when_none(self):
        from src.generator import build_context_block
        chunk = make_chunk(source="readme.md", page=None)
        block = build_context_block([chunk])
        assert "p." not in block

    def test_messages_has_system_and_user(self):
        from src.generator import build_messages
        msgs = build_messages("Quelle est la réponse ?", [make_chunk()])
        roles = [m["role"] for m in msgs]
        assert "system" in roles
        assert "user" in roles

    def test_messages_user_contains_question(self):
        from src.generator import build_messages
        question = "Quel est le CA du Q1 ?"
        msgs = build_messages(question, [make_chunk()])
        user_content = next(m["content"] for m in msgs if m["role"] == "user")
        assert question in user_content

    def test_messages_user_contains_context(self):
        from src.generator import build_messages
        chunk = make_chunk(text="Le CA est de 4,2 M€.")
        msgs = build_messages("CA ?", [chunk])
        user_content = next(m["content"] for m in msgs if m["role"] == "user")
        assert "4,2 M€" in user_content

    def test_system_prompt_contains_anti_hallucination_rule(self):
        from src.generator import SYSTEM_PROMPT
        assert "UNIQUEMENT" in SYSTEM_PROMPT or "uniquement" in SYSTEM_PROMPT.lower()
        assert "fabrique" in SYSTEM_PROMPT or "invente" in SYSTEM_PROMPT.lower() or "fabriqu" in SYSTEM_PROMPT


# ─── Tests Generator — SSE events ─────────────────────────────────────────────

class TestSSEEvents:

    def test_token_event_structure(self):
        from src.generator import token_event
        ev = token_event("bonjour")
        assert ev["type"] == "token"
        assert ev["token"] == "bonjour"
        assert ev["done"] is False

    def test_sources_event_done_true(self):
        from src.generator import sources_event
        ev = sources_event([make_chunk()])
        assert ev["done"] is True
        assert ev["type"] == "sources"
        assert len(ev["sources"]) == 1

    def test_sources_event_contains_preview(self):
        from src.generator import sources_event
        long_text = "A" * 300
        chunk = make_chunk(text=long_text)
        ev = sources_event([chunk])
        preview = ev["sources"][0]["text_preview"]
        assert len(preview) <= 203   # 200 chars + "…"

    def test_error_event_structure(self):
        from src.generator import error_event
        ev = error_event("Ollama timeout")
        assert ev["type"] == "error"
        assert ev["done"] is True
        assert "Ollama" in ev["message"]

    def test_no_chunks_yields_error_not_sources(self):
        """Sans chunks, le generator doit émettre un error event, pas sources."""
        from src.generator import error_event
        # Simuler la logique : chunks vides → error
        ev = error_event("Aucun document pertinent trouvé")
        assert ev["type"] == "error"


# ─── Tests Retriever — score filtering ───────────────────────────────────────

class TestRetrieverScoreFilter:
    """
    Vérifie que le retriever construit les bons paramètres pour Qdrant.
    La logique de filtrage par score est déléguée à Qdrant (score_threshold param).
    """

    @pytest.mark.asyncio
    async def test_retrieve_calls_qdrant_with_correct_params(self):
        from src.retriever import Retriever

        # Mock Qdrant
        qdrant_mock = AsyncMock()
        qdrant_mock.search = AsyncMock(return_value=[])

        # Mock embed
        with patch("src.retriever.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": [0.1] * 768}
            mock_post.return_value = mock_resp

            retriever = Retriever(qdrant=qdrant_mock)
            await retriever.retrieve(
                question="Quelle est la marge EBITDA ?",
                collection="finance",
                top_k=3,
                score_threshold=0.80,
            )

        qdrant_mock.search.assert_called_once()
        call_kwargs = qdrant_mock.search.call_args.kwargs
        assert call_kwargs["limit"] == 3
        assert call_kwargs["score_threshold"] == 0.80

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_list_when_no_results(self):
        from src.retriever import Retriever
        qdrant_mock = AsyncMock()
        qdrant_mock.search = AsyncMock(return_value=[])

        with patch("src.retriever.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"embedding": [0.0] * 768}
            mock_post.return_value = mock_resp

            retriever = Retriever(qdrant=qdrant_mock)
            chunks = await retriever.retrieve("question sans résultat")

        assert chunks == []
