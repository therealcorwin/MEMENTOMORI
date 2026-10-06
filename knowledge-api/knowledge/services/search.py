"""Service de recherche hybride pgvector + PostgreSQL tsvector + RRF selon §16.6 (Task 3.9)."""

import uuid
from dataclasses import dataclass
from typing import Any, List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.models import (
    Fragment,
    DocumentVersion,
    Document,
    Collection,
    CollectionWorkspace
)
from knowledge.services.reranker import rerank_candidates

logger = get_logger(__name__)

@dataclass
class SearchResult:
    fragment_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    version: int
    content: str
    context_prefix: Optional[str]
    page_number: Optional[int]
    score: float
    citation_ref: dict[str, Any]
    sensitivity: str
    scope: str


async def hybrid_search(
    query: str,
    query_embedding: List[float],
    workspace_ids: List[uuid.UUID],
    allowed_scopes: List[str],
    max_sensitivity: str,
    db: AsyncSession,
    top_k: int = 5,
    rrf_k: int = 60,
    use_reranker: bool = True,
) -> List[SearchResult]:
    """
    Exécute une recherche hybride (pgvector cosine + full-text french)
    avec triple filtrage de sécurité (workspace, scope, sensibilité) et fusion RRF.
    """
    logger.info(
        "hybrid_search_started",
        query=query[:60],
        workspaces=[str(w) for w in workspace_ids],
        scopes=allowed_scopes,
        max_sensitivity=max_sensitivity,
    )

    # Base join pour les filtres de sécurité
    base_join = (
        select(
            Fragment.id.label("frag_id"),
            Fragment.content,
            Fragment.context_prefix,
            Fragment.page_number,
            Fragment.citation_ref,
            Document.id.label("doc_id"),
            Document.title.label("doc_title"),
            Document.version.label("doc_version"),
            Document.sensitivity,
            Document.scope
        )
        .select_from(Fragment)
        .join(DocumentVersion, Fragment.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .join(Collection, Document.collection_id == Collection.id)
        .join(CollectionWorkspace, Collection.id == CollectionWorkspace.collection_id)
        .where(
            and_(
                CollectionWorkspace.workspace_id.in_(workspace_ids),
                Document.is_active == True,  # noqa: E712
                Document.scope.in_(allowed_scopes),
                func.sensitivity_level(Document.sensitivity) <= func.sensitivity_level(max_sensitivity),
            )
        )
    )

    # 1. Recherche vectorielle (Top 20 par distance cosine)
    vec_stmt = (
        base_join.add_columns(
            Fragment.embedding.cosine_distance(query_embedding).label("vec_distance")
        )
        .order_by("vec_distance")
        .limit(20)
    )
    vec_res = await db.execute(vec_stmt)
    vec_hits = vec_res.all()

    # 2. Recherche textuelle (Top 20 par ts_rank full-text french)
    clean_q = query.strip()
    fts_hits = []
    if clean_q:
        import re
        stop_words = {
            "quel", "quelle", "quels", "quelles", "dans", "pour", "cette", "sont",
            "avec", "est", "les", "des", "une", "par", "sur", "ont", "ete", "qui",
            "sous", "dont", "chez", "nous", "vous", "leur", "plus", "tout", "tous"
        }
        tokens = re.findall(r'\b[a-zA-Z0-9_\u00C0-\u017F]{3,}\b', clean_q.lower())
        meaningful = [t for t in tokens if t not in stop_words]

        try:
            if meaningful:
                or_expr = " | ".join(meaningful)
                fts_query = func.to_tsquery("french", or_expr)
            else:
                fts_query = func.plainto_tsquery("french", clean_q)

            fts_stmt = (
                base_join.add_columns(
                    func.ts_rank(Fragment.search_vector, fts_query).label("text_rank")
                )
                .where(Fragment.search_vector.op("@@")(fts_query))
                .order_by(func.ts_rank(Fragment.search_vector, fts_query).desc())
                .limit(20)
            )
            fts_res = await db.execute(fts_stmt)
            fts_hits = fts_res.all()
        except Exception:
            # Fallback en cas d'erreur de parsing to_tsquery
            fb_query = func.plainto_tsquery("french", clean_q)
            fts_stmt_fb = (
                base_join.add_columns(
                    func.ts_rank(Fragment.search_vector, fb_query).label("text_rank")
                )
                .where(Fragment.search_vector.op("@@")(fb_query))
                .order_by(func.ts_rank(Fragment.search_vector, fb_query).desc())
                .limit(20)
            )
            fts_res = await db.execute(fts_stmt_fb)
            fts_hits = fts_res.all()

    # 3. Fusion Reciprocal Rank Fusion (RRF)
    # Score RRF = 1 / (k + rank_vec) + weight_fts / (k + rank_text)
    scores: dict[uuid.UUID, float] = {}
    details: dict[uuid.UUID, Any] = {}

    for rank, row in enumerate(vec_hits, start=1):
        f_id = row.frag_id
        scores[f_id] = scores.get(f_id, 0.0) + (1.0 / (rrf_k + rank))
        details[f_id] = row

    # Les correspondances plein-texte exactes en français reçoivent une pondération renforcée (3.0)
    for rank, row in enumerate(fts_hits, start=1):
        f_id = row.frag_id
        scores[f_id] = scores.get(f_id, 0.0) + (3.0 / (rrf_k + rank))
        if f_id not in details:
            details[f_id] = row

    # Tri par score RRF décroissant
    candidate_limit = max(top_k * 2, 10) if use_reranker else top_k
    sorted_ids = sorted(scores.keys(), key=lambda fid: scores[fid], reverse=True)[:candidate_limit]

    candidates: List[SearchResult] = []
    for f_id in sorted_ids:
        row = details[f_id]
        candidates.append(
            SearchResult(
                fragment_id=row.frag_id,
                document_id=row.doc_id,
                document_title=row.doc_title,
                version=row.doc_version,
                content=row.content,
                context_prefix=row.context_prefix,
                page_number=row.page_number,
                score=round(scores[f_id], 5),
                citation_ref=row.citation_ref or {},
                sensitivity=row.sensitivity,
                scope=row.scope
            )
        )

    # 4. Reranker Cross-Encoder (§16.6, §17 B12)
    if use_reranker and candidates:
        results = await rerank_candidates(query=query, candidates=candidates, top_k=top_k)
    else:
        results = candidates[:top_k]

    logger.info("hybrid_search_completed", total_found=len(results), top_score=results[0].score if results else 0)
    return results
