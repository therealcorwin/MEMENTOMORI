"""Modèle Feedback (retours utilisateurs, §16.8)."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, Text, String, ForeignKey, DateTime, func, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.models.base import Base

class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id"),
        nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    workspace: Mapped[Optional["Workspace"]] = relationship("Workspace")

    __table_args__ = (
        CheckConstraint("rating IN ('good', 'bad', 'wrong')", name="check_feedback_rating"),
        Index("idx_feedback_rating", "rating", "created_at"),
    )
