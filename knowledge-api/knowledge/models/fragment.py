"""Modèle Fragment (chunks avec embeddings et tsvector)."""

import uuid
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import (
    Integer, Text, ForeignKey, DateTime, func, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from knowledge.models.base import Base

class Fragment(Base):
    __tablename__ = "fragments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[Any]] = mapped_column(Vector(768), nullable=True)
    citation_ref: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    context_prefix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    document_version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion", back_populates="fragments"
    )

    __table_args__ = (
        Index("idx_fragments_version", "document_version_id"),
        Index(
            "idx_fragments_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"}
        ),
        Index("idx_fragments_search", "search_vector", postgresql_using="gin"),
    )
