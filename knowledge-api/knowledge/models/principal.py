"""Modèles Principal et Policy (RBAC et contrôle d'accès)."""

import uuid
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import (
    String, ForeignKey, DateTime, func, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base

class Principal(Base):
    __tablename__ = "principals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    policies: Mapped[List["Policy"]] = relationship(
        "Policy", back_populates="principal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("type IN ('user', 'app', 'bot')", name="check_principal_type"),
    )


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_scopes: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["owner"], server_default='["owner"]'
    )
    actions: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["read"], server_default='["read"]'
    )
    max_sensitivity: Mapped[str] = mapped_column(
        String(16), default="interne", server_default="interne"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="policies")
    principal: Mapped["Principal"] = relationship("Principal", back_populates="policies")

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'cs', 'coproprietaire', 'reader', 'contributor')",
            name="check_policy_role"
        ),
        CheckConstraint(
            "max_sensitivity IN ('public', 'interne', 'confidentiel', 'secret')",
            name="check_policy_sensitivity"
        ),
        Index("idx_policies_workspace", "workspace_id"),
        Index("idx_policies_principal", "principal_id"),
    )
