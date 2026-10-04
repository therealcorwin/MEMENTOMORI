"""Modèles Source, Document et DocumentVersion."""

import uuid
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import (
    String, Boolean, Integer, Text, ForeignKey, DateTime, func, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base

class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False
    )
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    auto_approve: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="sources")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="source")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False
    )
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="recu", server_default="recu"
    )
    scope: Mapped[str] = mapped_column(
        String(64), default="owner", server_default="owner"
    )
    sensitivity: Mapped[str] = mapped_column(
        String(16), default="interne", server_default="interne"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    duplicate_of: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relations
    collection: Mapped["Collection"] = relationship("Collection", back_populates="documents")
    source: Mapped[Optional["Source"]] = relationship("Source", back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('recu','a_verifier','actif','archive','obsolete','rejete','supprime')",
            name="check_document_status"
        ),
        CheckConstraint(
            "sensitivity IN ('public', 'interne', 'confidentiel', 'secret')",
            name="check_document_sensitivity"
        ),
        Index("idx_documents_collection", "collection_id"),
        Index("idx_documents_scope", "scope"),
        Index("idx_documents_sensitivity", "sensitivity"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_hash", "content_hash"),
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    version_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    original_file_ref: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    fragments: Mapped[List["Fragment"]] = relationship(
        "Fragment", back_populates="document_version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("uq_doc_version", "document_id", "version_number", unique=True),
    )
