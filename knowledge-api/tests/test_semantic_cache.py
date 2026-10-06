"""Tests de validation du Cache Sémantique pgvector (§16.9, §17 B13)."""

import pytest
import uuid
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import (
    Workspace,
    Document,
    Collection,
    CollectionWorkspace,
    AnswerCache,
    AnswerCacheDeps,
)
from knowledge.services.answer_cache import AnswerCacheService


@pytest.mark.asyncio
async def test_exact_and_semantic_cache(db_session: AsyncSession):
    # 1. Création d'un workspace et d'un document de test
    ws = Workspace(
        name="WS Cache Test",
        slug=f"ws-cache-{uuid.uuid4().hex[:6]}",
        domain="pro",
    )
    col = Collection(name="Col Cache Test")
    db_session.add_all([ws, col])
    await db_session.flush()

    db_session.add(CollectionWorkspace(collection_id=col.id, workspace_id=ws.id))
    doc = Document(
        collection_id=col.id,
        title="Doc Cache Reglement",
        scope="copro",
        sensitivity="interne",
        version=1,
    )
    db_session.add(doc)
    await db_session.commit()

    cache_service = AnswerCacheService(db_session)

    # 2. Vecteur de référence normalisé (768 dimensions)
    # [1.0, 0.0, ..., 0.0]
    base_embedding = [0.0] * 768
    base_embedding[0] = 1.0

    sources = [{
        "document_id": str(doc.id),
        "document_title": doc.title,
        "version": 1,
    }]

    # 3. Enregistrement en cache avec vecteur
    await cache_service.set(
        question="Quels sont les horaires des travaux dans l'immeuble ?",
        workspace_id=ws.id,
        answer="Les travaux sont autorisés du lundi au vendredi de 8h à 19h.",
        sources=sources,
        confidence="high",
        model="gemini-1.5-flash",
        mode="answer",
        embedding=base_embedding,
    )

    try:
        # 4. Test HIT EXACT (question identique)
        exact_hit = await cache_service.get(
            question="Quels sont les horaires des travaux dans l'immeuble ?",
            workspace_id=ws.id,
            mode="answer",
        )
        assert exact_hit is not None
        assert exact_hit.cache_type == "exact"
        assert "8h à 19h" in exact_hit.answer

        # 5. Test HIT SÉMANTIQUE (question reformulée avec vecteur quasi identique)
        # Distance cosinus = 1 - (1.0 * 0.999) = 0.001 < 0.05 (similarité ~99.9%)
        similar_embedding = [0.0] * 768
        similar_embedding[0] = 0.999
        similar_embedding[1] = 0.0447  # norme = 1.0

        semantic_hit = await cache_service.get(
            question="horaires autorisés bricolage copro",
            workspace_id=ws.id,
            mode="answer",
            query_embedding=similar_embedding,
            semantic_threshold=0.95,
        )
        assert semantic_hit is not None
        assert semantic_hit.cache_type == "semantic"
        assert "8h à 19h" in semantic_hit.answer

        # 6. Test MISS SÉMANTIQUE (vecteur orthogonal ou trop éloigné)
        distant_embedding = [0.0] * 768
        distant_embedding[50] = 1.0  # distance = 1.0 >> 0.05

        miss_result = await cache_service.get(
            question="comment voter à l'assemblée générale",
            workspace_id=ws.id,
            mode="answer",
            query_embedding=distant_embedding,
            semantic_threshold=0.95,
        )
        assert miss_result is None

        # 7. Test INVALIDATION AUTOMATIQUE par mise à jour du document (§16.9)
        await db_session.execute(
            update(Document).where(Document.id == doc.id).values(version=2)
        )
        await db_session.commit()

        invalidated_hit = await cache_service.get(
            question="Quels sont les horaires des travaux dans l'immeuble ?",
            workspace_id=ws.id,
            mode="answer",
        )
        assert invalidated_hit is None
    finally:
        # Nettoyage systématique du workspace et des artefacts de cache test
        await db_session.execute(delete(AnswerCacheDeps).where(AnswerCacheDeps.document_id == doc.id))
        await db_session.execute(delete(AnswerCache).where(AnswerCache.workspace_id == ws.id))
        await db_session.execute(delete(Document).where(Document.id == doc.id))
        await db_session.execute(delete(CollectionWorkspace).where(CollectionWorkspace.workspace_id == ws.id))
        await db_session.execute(delete(Collection).where(Collection.id == col.id))
        await db_session.execute(delete(Workspace).where(Workspace.id == ws.id))
        await db_session.commit()
