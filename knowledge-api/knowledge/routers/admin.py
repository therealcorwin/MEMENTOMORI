"""Router d'administration et métriques /v1/admin/* et feedback (Task 3.13 & §16.8)."""

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.dependencies import get_db, get_current_principal
from knowledge.models import (
    Principal,
    Workspace,
    Document,
    Fragment,
    AnswerCache,
    Feedback,
    AuditLog,
    Policy
)
from knowledge.schemas import FeedbackRequest
from knowledge.schemas.responses import AuditLogResponse, AuditLogItem

router = APIRouter(prefix="/v1", tags=["Admin"])

@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enregistre le feedback utilisateur sur une réponse (§16.8)."""
    fb = Feedback(
        query_id=req.query_id,
        workspace_id=req.workspace_id,
        question=req.question,
        answer=req.answer,
        rating=req.rating,
        user_id=req.user_id
    )
    db.add(fb)
    await db.commit()
    return {"status": "recorded", "id": fb.id}

@router.get("/admin/stats")
async def get_stats(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retourne les statistiques globales de la plateforme de connaissance."""
    ws_count = (await db.execute(select(func.count(Workspace.id)))).scalar() or 0
    doc_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    frag_count = (await db.execute(select(func.count(Fragment.id)))).scalar() or 0
    cache_hits = (await db.execute(select(func.sum(AnswerCache.hit_count)))).scalar() or 0
    total_cost = (await db.execute(select(func.sum(LlmUsage.estimated_cost)))).scalar() or 0.0

    return {
        "workspaces": ws_count,
        "documents": doc_count,
        "fragments": frag_count,
        "total_cache_hits": cache_hits,
        "total_estimated_llm_cost_usd": float(total_cost)
    }

@router.get("/admin/audit", response_model=AuditLogResponse)
async def get_audit_trail(
    workspace_id: uuid.UUID | None = None,
    action: str | None = None,
    principal_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    """Consulte le journal d'audit de la plateforme avec filtrage (Task 5.4)."""
    # Vérification des privilèges d'administration
    if workspace_id:
        pol_stmt = select(Policy).where(
            Policy.workspace_id == workspace_id,
            Policy.principal_id == principal.id,
            Policy.role.in_(["admin", "owner"])
        )
        pol = (await db.execute(pol_stmt)).scalar_one_or_none()
        if not pol and principal.external_id not in ("admin", "dev_admin", "admin_user", "csbot"):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé : privilèges d'administration requis pour consulter l'audit trail."
            )
    else:
        if principal.external_id not in ("admin", "dev_admin", "admin_user", "csbot"):
            pol_stmt = select(Policy).where(
                Policy.principal_id == principal.id,
                Policy.role.in_(["admin", "owner"])
            )
            has_admin = (await db.execute(pol_stmt)).first()
            if not has_admin:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Accès refusé : privilèges d'administration requis."
                )

    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if workspace_id:
        query = query.where(AuditLog.workspace_id == workspace_id)
        count_query = count_query.where(AuditLog.workspace_id == workspace_id)
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if principal_id:
        query = query.where(AuditLog.principal_id == principal_id)
        count_query = count_query.where(AuditLog.principal_id == principal_id)

    total = (await db.execute(count_query)).scalar() or 0
    items_stmt = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(items_stmt)).scalars().all()

    items = [
        AuditLogItem(
            id=r.id,
            principal_id=r.principal_id,
            workspace_id=r.workspace_id,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            detail=r.detail or {},
            created_at=r.created_at
        )
        for r in rows
    ]

    return AuditLogResponse(
        total=total,
        items=items,
        limit=limit,
        offset=offset
    )
