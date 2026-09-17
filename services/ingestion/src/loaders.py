"""
Loaders de documents — interface unifiée pour PDF, Markdown, TXT, URL.
Chaque loader retourne une liste de (texte, métadonnées).
"""

from __future__ import annotations

import io
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger(__name__)


@dataclass
class RawDocument:
    """Document brut avant chunking."""
    text:        str
    source:      str
    source_type: str                    # pdf | md | txt | url | html
    metadata:    dict = field(default_factory=dict)


class DocumentLoader(Protocol):
    async def load(self, source: str) -> list[RawDocument]:
        ...


# ─── PDF ─────────────────────────────────────────────────────────────────────

class PDFLoader:
    """Extrait le texte d'un PDF page par page, conserve le numéro de page."""

    async def load(self, path: str) -> list[RawDocument]:
        from pypdf import PdfReader

        docs = []
        reader = PdfReader(path)
        filename = Path(path).name

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = _clean_text(text)
            if len(text.strip()) < 20:
                continue  # page vide ou image

            docs.append(RawDocument(
                text=text,
                source=filename,
                source_type="pdf",
                metadata={"page": i + 1, "total_pages": len(reader.pages)},
            ))

        logger.info("pdf_loaded", path=path, pages=len(docs))
        return docs


# ─── Markdown ────────────────────────────────────────────────────────────────

class MarkdownLoader:
    """Charge un fichier Markdown. Le texte est conservé tel quel (pas de rendu)."""

    async def load(self, path: str) -> list[RawDocument]:
        text = Path(path).read_text(encoding="utf-8")
        text = _clean_text(text)
        logger.info("md_loaded", path=path, chars=len(text))
        return [RawDocument(
            text=text,
            source=Path(path).name,
            source_type="md",
        )]


# ─── TXT ─────────────────────────────────────────────────────────────────────

class TXTLoader:
    async def load(self, path: str) -> list[RawDocument]:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        text = _clean_text(text)
        return [RawDocument(text=text, source=Path(path).name, source_type="txt")]


# ─── URL / HTML ───────────────────────────────────────────────────────────────

class URLLoader:
    """Télécharge une URL et extrait le texte visible (BeautifulSoup)."""

    async def load(self, url: str) -> list[RawDocument]:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "RAGBot/1.0 (document indexer)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Supprime les balises non-contenu
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        else:
            text = resp.text

        text = _clean_text(text)
        logger.info("url_loaded", url=url, chars=len(text))
        return [RawDocument(text=text, source=url, source_type="url")]


# ─── Factory ─────────────────────────────────────────────────────────────────

def get_loader(path_or_url: str) -> DocumentLoader:
    """Retourne le loader adapté au type de fichier ou d'URL."""
    if path_or_url.startswith(("http://", "https://")):
        return URLLoader()

    suffix = Path(path_or_url).suffix.lower()
    loaders: dict[str, DocumentLoader] = {
        ".pdf":  PDFLoader(),
        ".md":   MarkdownLoader(),
        ".txt":  TXTLoader(),
        ".text": TXTLoader(),
    }
    loader = loaders.get(suffix)
    if loader is None:
        # Fallback : essaie de détecter via mimetype
        mime, _ = mimetypes.guess_type(path_or_url)
        if mime and "pdf" in mime:
            return PDFLoader()
        raise ValueError(
            f"Format non supporté : {suffix!r}. "
            f"Formats acceptés : {list(loaders.keys())} + URLs"
        )
    return loader


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Nettoyage léger : lignes vides multiples, espaces superflus."""
    import re
    # Réduit les séquences de 3+ newlines en 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Supprime les espaces en fin de ligne
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()
