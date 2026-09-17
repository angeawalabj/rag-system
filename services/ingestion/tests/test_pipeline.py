"""
Tests unitaires — service d'ingestion.
Tout ce qui touche Ollama, Qdrant, PostgreSQL est mocké.
Exécution : pytest services/ingestion/tests/ -v
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Tests Loaders ─────────────────────────────────────────────────────────────

class TestLoaderFactory:
    """Vérifie que get_loader retourne le bon loader selon l'extension."""

    def test_pdf_loader(self):
        from src.loaders import get_loader, PDFLoader
        loader = get_loader("/tmp/rapport.pdf")
        assert isinstance(loader, PDFLoader)

    def test_md_loader(self):
        from src.loaders import get_loader, MarkdownLoader
        loader = get_loader("/tmp/README.md")
        assert isinstance(loader, MarkdownLoader)

    def test_txt_loader(self):
        from src.loaders import get_loader, TXTLoader
        loader = get_loader("/tmp/notes.txt")
        assert isinstance(loader, TXTLoader)

    def test_url_loader(self):
        from src.loaders import get_loader, URLLoader
        loader = get_loader("https://example.com/page")
        assert isinstance(loader, URLLoader)

    def test_unknown_format_raises(self):
        from src.loaders import get_loader
        with pytest.raises(ValueError, match="Format non supporté"):
            get_loader("/tmp/file.xyz")


class TestTextCleaning:
    """Vérifie le nettoyage du texte avant chunking."""

    def test_removes_triple_newlines(self):
        from src.loaders import _clean_text
        text = "paragraphe 1\n\n\n\nparagraphe 2"
        result = _clean_text(text)
        assert "\n\n\n" not in result
        assert "paragraphe 1" in result
        assert "paragraphe 2" in result

    def test_strips_trailing_spaces(self):
        from src.loaders import _clean_text
        text = "ligne avec espaces   \nautre ligne  "
        result = _clean_text(text)
        for line in result.split("\n"):
            assert not line.endswith(" ")

    def test_empty_text_returns_empty(self):
        from src.loaders import _clean_text
        assert _clean_text("") == ""
        assert _clean_text("   \n\n  ") == ""


class TestMarkdownLoader:
    """Teste le loader Markdown sur un fichier temporaire."""

    def test_load_markdown_file(self, tmp_path):
        content = "# Titre\n\nParagraphe de texte.\n\n## Section 2\n\nContenu."
        md_file = tmp_path / "test.md"
        md_file.write_text(content)

        from src.loaders import MarkdownLoader
        loader = MarkdownLoader()
        docs = asyncio.run(loader.load(str(md_file)))

        assert len(docs) == 1
        assert docs[0].source_type == "md"
        assert "Titre" in docs[0].text
        assert "Section 2" in docs[0].text

    def test_source_is_filename(self, tmp_path):
        md_file = tmp_path / "mon-doc.md"
        md_file.write_text("Contenu minimal.")

        from src.loaders import MarkdownLoader
        docs = asyncio.run(MarkdownLoader().load(str(md_file)))
        assert docs[0].source == "mon-doc.md"


# ─── Tests Chunker ────────────────────────────────────────────────────────────

class TestChunking:
    """Vérifie le comportement du RecursiveCharacterTextSplitter."""

    def _make_pipeline(self):
        """Crée un IngestionPipeline avec des mocks pour Qdrant et Session."""
        from src.pipeline import IngestionPipeline
        qdrant_mock  = AsyncMock()
        session_mock = AsyncMock()
        return IngestionPipeline(qdrant=qdrant_mock, session=session_mock)

    def test_short_text_single_chunk(self):
        pipeline = self._make_pipeline()
        from src.loaders import RawDocument
        raw = RawDocument(text="Texte court.", source="test.md", source_type="md")
        chunks = pipeline._chunk([raw], span=MagicMock(), log=MagicMock())
        assert len(chunks) >= 1
        assert chunks[0][0] == "Texte court."

    def test_long_text_multiple_chunks(self):
        pipeline = self._make_pipeline()
        from src.loaders import RawDocument
        # 5000 caractères → plusieurs chunks de 512
        long_text = "mot " * 1250
        raw = RawDocument(text=long_text, source="long.txt", source_type="txt")
        chunks = pipeline._chunk([raw], span=MagicMock(), log=MagicMock())
        assert len(chunks) > 1

    def test_chunk_metadata_contains_source(self):
        pipeline = self._make_pipeline()
        from src.loaders import RawDocument
        raw = RawDocument(
            text="Contenu.", source="rapport.pdf", source_type="pdf",
            metadata={"page": 3}
        )
        chunks = pipeline._chunk([raw], span=MagicMock(), log=MagicMock())
        _, meta = chunks[0]
        assert meta["source"] == "rapport.pdf"
        assert meta["source_type"] == "pdf"
        assert meta["page"] == 3
        assert "chunk_index" in meta
        assert "chunk_total" in meta

    def test_chunk_index_sequential(self):
        pipeline = self._make_pipeline()
        from src.loaders import RawDocument
        long_text = "paragraphe. " * 300
        raw = RawDocument(text=long_text, source="test.txt", source_type="txt")
        chunks = pipeline._chunk([raw], span=MagicMock(), log=MagicMock())
        indices = [meta["chunk_index"] for _, meta in chunks]
        assert indices == list(range(len(chunks)))


# ─── Tests Embedder ──────────────────────────────────────────────────────────

class TestEmbedder:
    """Teste le client Ollama avec un mock httpx."""

    @pytest.mark.asyncio
    async def test_embed_one_success(self):
        from src.embedder import Embedder

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1] * 768}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            async with Embedder() as embedder:
                vector = await embedder.embed_one("texte de test")

        assert len(vector) == 768
        assert vector[0] == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_embed_batch_returns_correct_count(self):
        from src.embedder import Embedder

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embedding": [0.5] * 768}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            async with Embedder() as embedder:
                vectors = await embedder.embed_batch(["chunk1", "chunk2", "chunk3"])

        assert len(vectors) == 3
        assert all(len(v) == 768 for v in vectors)

    @pytest.mark.asyncio
    async def test_embed_one_raises_on_empty_embedding(self):
        from src.embedder import Embedder, EmbedderError

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}  # pas de clé "embedding"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            with pytest.raises(EmbedderError, match="invalide"):
                async with Embedder() as embedder:
                    await embedder.embed_one("texte")


# ─── Tests Pipeline status ────────────────────────────────────────────────────

class TestPipelineStatusUpdates:
    """Vérifie que le pipeline met à jour correctement les statuts en DB."""

    @pytest.mark.asyncio
    async def test_status_set_to_processing_then_completed(self):
        from src.pipeline import IngestionPipeline
        from src.database import Document, IngestionStatus

        qdrant_mock  = AsyncMock()
        session_mock = AsyncMock()
        session_mock.commit = AsyncMock()

        pipeline = IngestionPipeline(qdrant=qdrant_mock, session=session_mock)
        doc = Document(
            id=uuid.uuid4(), filename="test.txt",
            source_type="txt", status=IngestionStatus.PENDING,
        )

        await pipeline._update_status(doc, IngestionStatus.PROCESSING)
        assert doc.status == IngestionStatus.PROCESSING

        await pipeline._update_status(doc, IngestionStatus.COMPLETED, chunk_count=5)
        assert doc.status == IngestionStatus.COMPLETED
        assert doc.chunk_count == 5
        assert doc.ingested_at is not None

    @pytest.mark.asyncio
    async def test_status_failed_stores_error_message(self):
        from src.pipeline import IngestionPipeline
        from src.database import Document, IngestionStatus

        pipeline = IngestionPipeline(
            qdrant=AsyncMock(), session=AsyncMock()
        )
        pipeline._session.commit = AsyncMock()

        doc = Document(
            id=uuid.uuid4(), filename="bad.pdf",
            source_type="pdf", status=IngestionStatus.PENDING,
        )

        err = "Ollama unreachable: connection refused"
        await pipeline._update_status(doc, IngestionStatus.FAILED, error=err)
        assert doc.status == IngestionStatus.FAILED
        assert err in doc.error_message
