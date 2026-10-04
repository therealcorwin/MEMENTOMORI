"""Modèle LlmUsage (suivi de la consommation LLM et coûts, §14.10)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    BigInteger, String, Integer, Numeric, Text, ForeignKey, DateTime, func, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base

class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id"),
        nullable=True
    )
    principal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id"),
        nullable=True
    )
    request_type: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), default=Decimal("0.0"), server_default="0"
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    principal: Mapped[Optional["Principal"]] = relationship("Principal")
    workspace: Mapped[Optional["Workspace"]] = relationship("Workspace")

    __table_args__ = (
        CheckConstraint(
            "request_type IN ('answer', 'embedding', 'classify')",
            name="check_llm_usage_request_type"
        ),
        Index("idx_llm_usage_workspace", "workspace_id", "created_at"),
        Index("idx_llm_usage_model", "model", "created_at"),
    )
