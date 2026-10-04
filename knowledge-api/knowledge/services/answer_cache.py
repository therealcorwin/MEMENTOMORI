"""Service de cache intelligent lié aux versions de documents (§16.9, Task 3.11)."""

import hashlib
import uuid
from typing import Any, List, Optional, Tuple
from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.models import AnswerCache, AnswerCacheDeps, Document

logger = get_logger(__name__)

class AnswerCacheService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def compute_hash(question: str, workspace_id: uuid.UUID, mode: str = "answer") -> str:
        """Calcule le hash SHA-256 de la question normalisée, du workspace et du mode."""
        norm_q = question.strip().lower()
        raw = f"{norm_q}:{str(workspace_id)}:{mode}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def get(
        self,
        question: str,
        workspace_id: uuid.UUID,
        mode: str = "answer"
    ) -> Optional[Tuple[str, str, dict[str, Any]]]:
        """
        Recherche une réponse en cache et vérifie l'invalidation par version (§16.9).
        Retourne (answer, confidence, sources_json) ou None si miss/invalidé.
        """
        q_hash = self.compute_hash(question, workspace_id, mode)

        stmt = select(AnswerCache).where(
            AnswerCache.question_hash == q_hash,
            AnswerCache.workspace_id == workspace_id
        )
        res = await self.db.execute(stmt)
        entry = res.scalar_one_or_none()
        if not entry:
            return None

        # Vérification des dépendances documents
        deps_stmt = select(AnswerCacheDeps, Document).join(
            Document, AnswerCacheDeps.document_id == Document.id
        ).where(AnswerCacheDeps.cache_id == entry.id)

        deps_res = await self.db.execute(deps_stmt)
        deps = deps_res.all()

        is_stale = False
        for dep, doc in deps:
            # Si le document a été modifié (nouvelle version) ou désactivé -> Cache obsolète
            if doc.version != dep.document_version or not doc.is_active:
                is_stale = True
                break

        if is_stale:
            logger.info("cache_invalidated_by_document_update", cache_id=entry.id)
            await self.db.execute(delete(AnswerCache).where(AnswerCache.id == entry.id))
            await self.db.commit()
            return None

        # Cache HIT : mise à jour des statistiques
        await self.db.execute(
            update(AnswerCache)
            .where(AnswerCache.id == entry.id)
            .values(
                hit_count=AnswerCache.hit_count + 1,
                last_hit_at=func.now()
            )
        )
        await self.db.commit()

        logger.info("cache_hit", cache_id=entry.id, hits=entry.hit_count + 1)
        return entry.answer, entry.confidence or "high", entry.sources_json

    async def set(
        self,
        question: str,
        workspace_id: uuid.UUID,
        answer: str,
        sources: List[dict[str, Any]],
        confidence: str = "high",
        model: str = "gemini-1.5-flash",
        mode: str = "answer"
    ) -> None:
        """Enregistre une réponse et ses dépendances documents en cache."""
        q_hash = self.compute_hash(question, workspace_id, mode)

        # Nettoyage d'une éventuelle ancienne entrée pour ce hash
        await self.db.execute(
            delete(AnswerCache).where(
                AnswerCache.question_hash == q_hash,
                AnswerCache.workspace_id == workspace_id
            )
        )

        entry = AnswerCache(
            question_hash=q_hash,
            question=question,
            workspace_id=workspace_id,
            answer=answer,
            confidence=confidence,
            model=model,
            sources_json={"sources": sources},
            hit_count=0
        )
        self.db.add(entry)
        await self.db.flush()

        # Enregistrement des dépendances
        seen_docs = set()
        for s in sources:
            doc_id_str = s.get("document_id")
            if not doc_id_str:
                continue
            doc_id = uuid.UUID(doc_id_str) if isinstance(doc_id_str, str) else doc_id_str
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)

            version = s.get("version", 1)
            dep = AnswerCacheDeps(
                cache_id=entry.id,
                document_id=doc_id,
                document_version=version
            )
            self.db.add(dep)

        await self.db.commit()
        logger.info("cache_stored", cache_id=entry.id, doc_deps_count=len(seen_docs))
