"""Modèles AnswerCache et AnswerCacheDeps (Cache intelligent lié aux versions, §16.9)."""

import uuid
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import (
    BigInteger, Text, String, Integer, ForeignKey, DateTime, func, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base

class AnswerCache(Base):
    __tablename__ = "answer_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False
    )
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sources_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relations
    workspace: Mapped["Workspace"] = relationship("Workspace")
    dependencies: Mapped[List["AnswerCacheDeps"]] = relationship(
        "AnswerCacheDeps", back_populates="cache_entry", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_cache_hash_ws", "question_hash", "workspace_id", unique=True),
        Index("idx_cache_hits", "hit_count"),
    )


class AnswerCacheDeps(Base):
    __tablename__ = "answer_cache_deps"

    cache_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("answer_cache.id", ondelete="CASCADE"),
        primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True
    )
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relations
    cache_entry: Mapped["AnswerCache"] = relationship("AnswerCache", back_populates="dependencies")
    document: Mapped["Document"] = relationship("Document")

    __table_args__ = (
        Index("idx_cache_deps_doc", "document_id"),
    )
