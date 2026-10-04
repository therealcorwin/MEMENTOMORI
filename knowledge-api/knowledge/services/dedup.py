"""Service de déduplication SHA-256 selon §16.4 (Task 3.7)."""

import hashlib
import re
import uuid
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.models import Document

logger = get_logger(__name__)

def normalize_text(text: str) -> str:
    """Normalise le texte pour le hachage (suppression des espaces multiples, minuscules)."""
    text = re.sub(r"\s+", " ", text.strip().lower())
    return text

def compute_content_hash(content: str) -> str:
    """Calcule l'empreinte SHA-256 d'un texte normalisé."""
    normalized = normalize_text(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

async def check_duplicate(
    content: str,
    db: AsyncSession,
    source_id: Optional[uuid.UUID] = None,
    collection_id: Optional[uuid.UUID] = None,
) -> Tuple[bool, Optional[uuid.UUID], str]:
    """
    Vérifie si un document est un doublon selon §16.4.
    Retourne (is_duplicate, duplicate_of_id, reason).
    """
    content_hash = compute_content_hash(content)

    # Recherche par hash identique
    stmt = select(Document).where(
        Document.content_hash == content_hash,
        Document.is_active == True  # noqa: E712
    )
    if collection_id:
        stmt = stmt.where(Document.collection_id == collection_id)

    result = await db.execute(stmt)
    existing_doc = result.scalar_one_or_none()

    if existing_doc:
        if source_id and existing_doc.source_id == source_id:
            logger.info("exact_duplicate_same_source", doc_id=str(existing_doc.id))
            return True, existing_doc.id, "exact_duplicate"
        else:
            logger.info("duplicate_detected_cross_source", doc_id=str(existing_doc.id))
            return True, existing_doc.id, "cross_source_duplicate"

    return False, None, "unique"
