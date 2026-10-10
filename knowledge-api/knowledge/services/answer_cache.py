"""Service de cache intelligent et sémantique lié aux versions de documents (§16.9, §17 B13)."""

import hashlib
import uuid
from typing import Any, List, Optional, Tuple
from sqlalchemy import select, delete, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.models import AnswerCache, AnswerCacheDeps, Document

logger = get_logger(__name__)


class CacheLookupResult(tuple):
    """Résultat de consultation de cache, rétrocompatible avec le déballage 3-tuple."""

    answer: str
    confidence: str
    sources_json: dict[str, Any]
    cache_type: str

    def __new__(
        cls,
        answer: str,
        confidence: str,
        sources_json: dict[str, Any],
        cache_type: str = "exact",
    ):
        t = super().__new__(cls, (answer, confidence, sources_json))
        t.answer = answer
        t.confidence = confidence
        t.sources_json = sources_json
        t.cache_type = cache_type
        return t


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
        mode: str = "answer",
        query_embedding: Optional[List[float]] = None,
        semantic_threshold: float = 0.95,
    ) -> Optional[CacheLookupResult]:
        """
        Recherche une réponse en cache avec double niveau :
        1. Cache exact SHA-256 (O(1), §16.9)
        2. Cache sémantique vectoriel pgvector (similarité cosinus >= semantic_threshold, §17 B13)
        Vérifie l'invalidation automatique par version de document.
        """
        entry: Optional[AnswerCache] = None
        match_type = "exact"

        # 1. Vérification par hash exact
        q_hash = self.compute_hash(question, workspace_id, mode)
        stmt = select(AnswerCache).where(
            AnswerCache.question_hash == q_hash,
            AnswerCache.workspace_id == workspace_id,
        )
        res = await self.db.execute(stmt)
        entry = res.scalar_one_or_none()

        # 2. Si miss exact et embedding disponible : recherche sémantique (§17 B13)
        if not entry and query_embedding:
            # Distance cosinus max = 1 - threshold (ex: 1 - 0.95 = 0.05)
            max_distance = 1.0 - semantic_threshold
            dist_col = AnswerCache.embedding.cosine_distance(query_embedding).label("dist")
            sem_stmt = (
                select(
                    AnswerCache,
                    dist_col,
                )
                .where(
                    and_(
                        AnswerCache.workspace_id == workspace_id,
                        AnswerCache.embedding.is_not(None),
                    )
                )
                .order_by(dist_col)
                .limit(1)
            )
            sem_res = await self.db.execute(sem_stmt)  # skylos: ignore [SKY-D211]
            sem_row = sem_res.first()
            if sem_row and sem_row.dist <= max_distance:
                entry = sem_row[0]
                match_type = "semantic"
                logger.info(
                    "semantic_cache_hit_found",
                    cache_id=entry.id,
                    similarity=round(1.0 - sem_row.dist, 4),
                    cached_q=entry.question[:50],
                    target_q=question[:50],
                )

        if not entry:
            return None

        # 3. Vérification des dépendances documentaires (§16.9)
        deps_stmt = (
            select(AnswerCacheDeps, Document)
            .join(Document, AnswerCacheDeps.document_id == Document.id)
            .where(AnswerCacheDeps.cache_id == entry.id)
        )
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

        # 4. Cache HIT : mise à jour des statistiques
        await self.db.execute(
            update(AnswerCache)
            .where(AnswerCache.id == entry.id)
            .values(
                hit_count=AnswerCache.hit_count + 1,
                last_hit_at=func.now(),
            )
        )
        await self.db.commit()

        logger.info(
            "cache_hit",
            cache_id=entry.id,
            match_type=match_type,
            hits=entry.hit_count + 1,
        )
        return CacheLookupResult(
            answer=entry.answer,
            confidence=entry.confidence or "high",
            sources_json=entry.sources_json,
            cache_type=match_type,
        )

    async def set(
        self,
        question: str,
        workspace_id: uuid.UUID,
        answer: str,
        sources: List[dict[str, Any]],
        confidence: str = "high",
        model: str = "gemini-1.5-flash",
        mode: str = "answer",
        embedding: Optional[List[float]] = None,
    ) -> None:
        """Enregistre une réponse, son vecteur et ses dépendances documents en cache."""
        q_hash = self.compute_hash(question, workspace_id, mode)

        # Nettoyage d'une éventuelle ancienne entrée pour ce hash
        await self.db.execute(
            delete(AnswerCache).where(
                AnswerCache.question_hash == q_hash,
                AnswerCache.workspace_id == workspace_id,
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
            embedding=embedding,
            hit_count=0,
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
                document_version=version,
            )
            self.db.add(dep)

        await self.db.commit()
        logger.info(
            "cache_stored",
            cache_id=entry.id,
            has_embedding=embedding is not None,
            doc_deps_count=len(seen_docs),
        )
