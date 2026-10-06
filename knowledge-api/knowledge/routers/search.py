"""Router de recherche documentaire hybride POST /v1/search (Task 3.13)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.dependencies import get_db, get_auth_context, get_current_principal, AuthContext
from knowledge.logging import get_logger
from knowledge.models import AuditLog, Principal
from knowledge.schemas import SearchRequest, SearchResponse, SearchResultItem
from knowledge.services.embedding import generate_embedding
from knowledge.services.search import hybrid_search

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Search"])

@router.post("/search", response_model=SearchResponse)
async def search_documents(
    req: SearchRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Recherche hybride vectorielle et plein-texte avec triple filtrage RBAC (§16.6)."""
    # Résolution des droits sur le workspace
    auth_ctx: AuthContext = await get_auth_context(
        workspace_id=req.workspace_id,
        principal=principal,
        db=db
    )

    logger.info(
        "search_request_received",
        principal=auth_ctx.principal.external_id,
        workspace=str(req.workspace_id),
        query=req.query[:80],
        trace_id=req.trace_id,
    )

    # 1. Calcul de l'embedding de la question
    query_emb = await generate_embedding(req.query)

    # 2. Exécution de la recherche hybride avec RBAC
    results = await hybrid_search(
        query=req.query,
        query_embedding=query_emb,
        workspace_ids=[auth_ctx.workspace.id],
        allowed_scopes=auth_ctx.allowed_scopes,
        max_sensitivity=auth_ctx.max_sensitivity,
        db=db,
        top_k=req.top_k,
    )

    # 3. Journal d'audit (§14.12)
    audit = AuditLog(
        principal_id=auth_ctx.principal.id,
        workspace_id=auth_ctx.workspace.id,
        action="search",
        target_type="workspace",
        target_id=auth_ctx.workspace.id,
        detail={
            "query": req.query,
            "results_count": len(results),
            "trace_id": req.trace_id
        }
    )
    db.add(audit)
    await db.commit()

    items = [
        SearchResultItem(
            fragment_id=r.fragment_id,
            document_id=r.document_id,
            document_title=r.document_title,
            version=r.version,
            content=r.content,
            score=r.score,
            page_number=r.page_number,
            sensitivity=r.sensitivity,
            scope=r.scope,
            citation_ref=r.citation_ref
        )
        for r in results
    ]

    return SearchResponse(
        query=req.query,
        total=len(items),
        results=items,
        trace_id=req.trace_id
    )
