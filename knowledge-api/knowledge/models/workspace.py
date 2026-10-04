"""Modèles Workspace, Collection et CollectionWorkspace."""

import uuid
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import String, ForeignKey, DateTime, func, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(
        String(16), default="pro", server_default="pro", nullable=False
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relations
    collections: Mapped[List["Collection"]] = relationship(
        "Collection",
        secondary="collection_workspaces",
        back_populates="workspaces"
    )
    sources: Mapped[List["Source"]] = relationship(
        "Source", back_populates="workspace", cascade="all, delete-orphan"
    )
    policies: Mapped[List["Policy"]] = relationship(
        "Policy", back_populates="workspace", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("domain IN ('perso', 'pro')", name="check_workspace_domain"),
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(
        String(32), default="prive", server_default="prive"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace",
        secondary="collection_workspaces",
        back_populates="collections"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="collection", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "classification IN ('prive', 'equipe', 'partage', 'confidentiel')",
            name="check_collection_classification"
        ),
    )


class CollectionWorkspace(Base):
    __tablename__ = "collection_workspaces"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True
    )
