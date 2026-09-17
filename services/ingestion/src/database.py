"""
Modèles SQLAlchemy et session async PostgreSQL.
Reflète le schéma défini dans infra/docker/init-db/01-schema.sql
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger, DateTime, Enum, Integer, String, Text, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import settings


# ─── Engine ──────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.postgres_dsn,
    pool_size=5,
    max_overflow=10,
    echo=(settings.log_level == "DEBUG"),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ─── Modèles ──────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class IngestionStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"


class Document(Base):
    """
    Représente un document ingéré (fichier ou URL).
    Un document → N chunks dans Qdrant.
    """
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename:    Mapped[str]            = mapped_column(String(512))
    source_type: Mapped[str]            = mapped_column(String(32))   # pdf, md, txt, url
    source_url:  Mapped[str | None]     = mapped_column(Text, nullable=True)
    collection:  Mapped[str]            = mapped_column(String(128), default="documents")
    status:      Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus), default=IngestionStatus.PENDING
    )
    chunk_count:    Mapped[int | None]  = mapped_column(Integer, nullable=True)
    error_message:  Mapped[str | None]  = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ingested_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:     Mapped[datetime]    = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at:     Mapped[datetime]    = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"
