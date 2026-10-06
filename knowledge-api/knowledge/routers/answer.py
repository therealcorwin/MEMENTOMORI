"""Router de réponse étayée POST /v1/answer avec cache intelligent (§16.9, Task 3.13)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.dependencies import get_db, get_auth_context, get_current_principal, AuthContext
from knowledge.logging import get_logger
from knowledge.models import AuditLog, Principal
from knowledge.schemas import AnswerRequest, AnswerResponse, SourceCitation
from knowledge.services.answer_cache import AnswerCacheService
from knowledge.services.embedding import generate_embedding
from knowledge.services.generation import generate_grounded_answer
from knowledge.services.search import hybrid_search

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Answer"])

@router.post("/answer", response_model=AnswerResponse)
async def answer_question(
    req: AnswerRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> AnswerResponse:
    """Génération de réponse RAG étayée par les documents avec citations strictes et cache intelligent."""
    auth_ctx: AuthContext = await get_auth_context(
        workspace_id=req.workspace_id,
        principal=principal,
        db=db
    )

    logger.info(
        "answer_request_received",
        principal=auth_ctx.principal.external_id,
        workspace=str(req.workspace_id),
        query=req.query[:80],
        use_cache=req.use_cache,
        trace_id=req.trace_id,
    )

    cache_service = AnswerCacheService(db)

    # 1. Vérification du cache intelligent exact (§16.9)
    if req.use_cache:
        cached_result = await cache_service.get(
            question=req.query,
            workspace_id=auth_ctx.workspace.id,
            mode="answer"
        )
        if cached_result:
            ans_text, confidence, sources_json = cached_result
            raw_sources = sources_json.get("sources", [])
            sources = [SourceCitation(**s) for s in raw_sources]
            citations = [s.document_title for s in sources]
            
            return AnswerResponse(
                query=req.query,
                answer=ans_text,
                confidence=1.0 if confidence == "high" else 0.8,
                sources=sources,
                citations=citations,
                limits=None,
                cached=True,
                cache_type=cached_result.cache_type,
                model="cache",
                provider="cache",
                warning=None,
                trace_id=req.trace_id,
                grounding_score=1.0,
                grounding_verified=True,
            )

    # 2. Embedding de la question
    query_emb = await generate_embedding(req.query)

    # 2b. Vérification du cache sémantique vectoriel pgvector (§17 B13)
    if req.use_cache:
        sem_cached_result = await cache_service.get(
            question=req.query,
            workspace_id=auth_ctx.workspace.id,
            mode="answer",
            query_embedding=query_emb,
            semantic_threshold=0.95
        )
        if sem_cached_result:
            ans_text, confidence, sources_json = sem_cached_result
            raw_sources = sources_json.get("sources", [])
            sources = [SourceCitation(**s) for s in raw_sources]
            citations = [s.document_title for s in sources]
            
            return AnswerResponse(
                query=req.query,
                answer=ans_text,
                confidence=0.95 if confidence == "high" else 0.8,
                sources=sources,
                citations=citations,
                limits=None,
                cached=True,
                cache_type="semantic",
                model="cache",
                provider="cache",
                warning=None,
                trace_id=req.trace_id,
                grounding_score=1.0,
                grounding_verified=True,
            )

    # 3. Recherche hybride avec RBAC et Reranker contextuel (§16.6, §17 B12)
    fragments = await hybrid_search(
        query=req.query,
        query_embedding=query_emb,
        workspace_ids=[auth_ctx.workspace.id],
        allowed_scopes=auth_ctx.allowed_scopes,
        max_sensitivity=auth_ctx.max_sensitivity,
        db=db,
        top_k=req.top_k,
    )

    # 4. Synthèse étayée par LLM avec citations, fallback et grounding check (§17 B11)
    gen_result = await generate_grounded_answer(
        question=req.query,
        fragments=fragments,
        workspace_id=auth_ctx.workspace.id,
        principal_id=auth_ctx.principal.id,
        db=db
    )

    sources = [SourceCitation(**s) for s in gen_result["sources"]]

    # 5. Enregistrement en cache avec vecteur si réponse trouvée et autorisée
    if req.use_cache and gen_result["sources"]:
        await cache_service.set(
            question=req.query,
            workspace_id=auth_ctx.workspace.id,
            answer=gen_result["answer"],
            sources=gen_result["sources"],
            confidence=str(gen_result["confidence"]),
            model=gen_result["model"],
            mode="answer",
            embedding=query_emb,
        )

    # 6. Journal d'audit
    audit = AuditLog(
        principal_id=auth_ctx.principal.id,
        workspace_id=auth_ctx.workspace.id,
        action="answer",
        target_type="workspace",
        target_id=auth_ctx.workspace.id,
        detail={
            "query": req.query,
            "confidence": gen_result["confidence"],
            "model": gen_result["model"],
            "provider": gen_result["provider"],
            "sources_count": len(sources),
            "grounding_score": gen_result.get("grounding_score"),
            "grounding_verified": gen_result.get("grounding_verified"),
            "trace_id": req.trace_id
        }
    )
    db.add(audit)
    await db.commit()

    return AnswerResponse(
        query=req.query,
        answer=gen_result["answer"],
        confidence=gen_result["confidence"],
        sources=sources,
        citations=gen_result["citations"],
        limits=gen_result["limits"],
        cached=False,
        cache_type=None,
        model=gen_result["model"],
        provider=gen_result["provider"],
        warning=gen_result["warning"],
        trace_id=req.trace_id,
        grounding_score=gen_result.get("grounding_score"),
        grounding_verified=gen_result.get("grounding_verified"),
    )
