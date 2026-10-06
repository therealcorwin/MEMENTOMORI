"""
Router d'administration complet /v1/admin/* et feedback (Sprint 8, §14.8 & §14.9-10).
Fournit les points d'accès requis pour le dashboard React (KPIs, explorateur, validation, audit, monitoring).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_, delete, update, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from knowledge.dependencies import get_db, get_current_principal
from knowledge.logging import get_logger
from knowledge.models import (
    Principal,
    Workspace,
    Collection,
    CollectionWorkspace,
    Source,
    Document,
    DocumentVersion,
    Fragment,
    AnswerCache,
    Feedback,
    AuditLog,
    Policy,
    LlmUsage,
)
from knowledge.schemas import FeedbackRequest
from knowledge.schemas.responses import AuditLogResponse, AuditLogItem
from knowledge.services.health import check_all_services

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Admin"])


# --- Schemas de Requête pour l'Administration ---
class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    sensitivity: Optional[str] = None
    scope: Optional[str] = None


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=64)
    domain: str = Field("pro", pattern="^(perso|pro)$")
    settings: dict[str, Any] = Field(default_factory=dict)


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


# --- Dépendance de Sécurité Administrateur ---
async def require_admin_access(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db)
) -> Principal:
    """Vérifie que l'utilisateur a les droits d'administration globale ou owner (§14.8)."""
    if getattr(principal, "is_admin", False) or principal.external_id in ("admin", "dev_admin", "admin_user", "owner", "csbot", "akadmin"):
        return principal

    pol = (await db.execute(
        select(Policy).where(
            Policy.principal_id == principal.id,
            Policy.role.in_(["admin", "owner"])
        )
    )).first()

    if not pol:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : privilèges d'administration requis."
        )
    return principal


# =====================================================================
# 1. FEEDBACK UTILISATEUR
# =====================================================================
@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
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


# =====================================================================
# 2. STATISTIQUES GLOBALES & KPIS (Home Page)
# =====================================================================
@router.get("/admin/stats")
async def get_stats(
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne les KPIs et indicateurs synthétiques de la plateforme (§14.4)."""
    ws_count = (await db.execute(select(func.count(Workspace.id)))).scalar() or 0
    doc_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    frag_count = (await db.execute(select(func.count(Fragment.id)))).scalar() or 0
    cache_hits = (await db.execute(select(func.sum(AnswerCache.hit_count)))).scalar() or 0
    total_cost = (await db.execute(select(func.sum(LlmUsage.estimated_cost)))).scalar() or Decimal("0.0")

    # Documents en attente de validation
    pending_count = (await db.execute(
        select(func.count(Document.id)).where(Document.status == "a_verifier")
    )).scalar() or 0

    # Documents par status
    status_query = select(Document.status, func.count(Document.id)).group_by(Document.status)
    status_counts = dict((await db.execute(status_query)).all())

    # Documents par workspace
    ws_docs_query = (
        select(Workspace.slug, Workspace.name, func.count(Document.id))
        .join(CollectionWorkspace, CollectionWorkspace.workspace_id == Workspace.id)
        .join(Document, Document.collection_id == CollectionWorkspace.collection_id)
        .group_by(Workspace.slug, Workspace.name)
    )
    docs_by_ws = [
        {"slug": slug, "name": name, "count": count}
        for slug, name, count in (await db.execute(ws_docs_query)).all()
    ]

    # Dernières ingestions (10 derniers documents)
    recent_docs_query = (
        select(Document.id, Document.title, Document.status, Document.created_at)
        .order_by(Document.created_at.desc())
        .limit(10)
    )
    recent_docs = [
        {
            "id": str(d.id),
            "title": d.title,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None
        }
        for d in (await db.execute(recent_docs_query)).all()
    ]

    return {
        "workspaces": ws_count,
        "documents": doc_count,
        "fragments": frag_count,
        "pending_validation": pending_count,
        "total_cache_hits": cache_hits,
        "total_estimated_llm_cost_usd": float(total_cost),
        "status_distribution": status_counts,
        "documents_by_workspace": docs_by_ws,
        "recent_ingestions": recent_docs
    }


# =====================================================================
# 3. GESTION DES DOCUMENTS (Explorateur & File de Validation)
# =====================================================================
@router.get("/admin/documents")
async def list_documents(
    workspace_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    sensitivity: Optional[str] = None,
    collection_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Liste paginée et filtrable des documents de la base (§14.4)."""
    query = select(Document).options(selectinload(Document.collection))
    count_query = select(func.count(Document.id))

    filters = []
    if status:
        filters.append(Document.status == status)
    if sensitivity:
        filters.append(Document.sensitivity == sensitivity)
    if collection_id:
        filters.append(Document.collection_id == collection_id)
    if search:
        filters.append(Document.title.ilike(f"%{search}%"))

    if workspace_id:
        query = query.join(CollectionWorkspace, CollectionWorkspace.collection_id == Document.collection_id)
        count_query = count_query.join(CollectionWorkspace, CollectionWorkspace.collection_id == Document.collection_id)
        filters.append(CollectionWorkspace.workspace_id == workspace_id)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0
    docs = (await db.execute(query.order_by(Document.created_at.desc()).offset(offset).limit(limit))).scalars().all()

    items = []
    for d in docs:
        items.append({
            "id": str(d.id),
            "title": d.title,
            "collection_id": str(d.collection_id),
            "collection_name": d.collection.name if d.collection else "N/A",
            "status": d.status,
            "scope": d.scope,
            "sensitivity": d.sensitivity,
            "version": d.version,
            "is_active": d.is_active,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "metadata": d.metadata_ or {}
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items
    }


@router.get("/admin/documents/{doc_id}")
async def get_document_detail(
    doc_id: uuid.UUID,
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne le détail complet d'un document avec ses versions et fragments (§14.4)."""
    doc = (await db.execute(
        select(Document)
        .options(selectinload(Document.collection), selectinload(Document.versions))
        .where(Document.id == doc_id)
    )).scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable.")

    # Récupérer les fragments associés
    frags_stmt = (
        select(Fragment)
        .join(DocumentVersion, Fragment.document_version_id == DocumentVersion.id)
        .where(DocumentVersion.document_id == doc_id)
        .order_by(Fragment.chunk_index)
    )
    frags = (await db.execute(frags_stmt)).scalars().all()

    extracted_text = doc.versions[0].extracted_text if doc.versions else ""

    return {
        "id": str(doc.id),
        "title": doc.title,
        "collection_id": str(doc.collection_id),
        "collection_name": doc.collection.name if doc.collection else "N/A",
        "status": doc.status,
        "scope": doc.scope,
        "sensitivity": doc.sensitivity,
        "version": doc.version,
        "is_active": doc.is_active,
        "content_hash": doc.content_hash,
        "metadata": doc.metadata_ or {},
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "extracted_text": extracted_text,
        "fragments_count": len(frags),
        "versions": [
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "original_file_ref": v.original_file_ref,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in (doc.versions or [])
        ],
        "fragments": [
            {
                "id": str(f.id),
                "chunk_index": f.chunk_index,
                "context_prefix": f.context_prefix,
                "page_number": f.page_number,
                "content_preview": f.content[:300] + ("..." if len(f.content) > 300 else "")
            }
            for f in frags
        ]
    }


@router.patch("/admin/documents/{doc_id}")
async def update_document(
    doc_id: uuid.UUID,
    req: DocumentUpdateRequest,
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Modifie le statut, la sensibilité ou le scope d'un document (§14.4)."""
    doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable.")

    changes: dict[str, Any] = {}
    if req.title is not None:
        doc.title = req.title
        changes["title"] = req.title
    if req.status is not None:
        if req.status not in ('recu', 'a_verifier', 'actif', 'archive', 'obsolete', 'rejete', 'supprime'):
            raise HTTPException(status_code=400, detail=f"Statut invalide : {req.status}")
        doc.status = req.status
        changes["status"] = req.status
    if req.sensitivity is not None:
        if req.sensitivity not in ('public', 'interne', 'confidentiel', 'secret'):
            raise HTTPException(status_code=400, detail=f"Sensibilité invalide : {req.sensitivity}")
        doc.sensitivity = req.sensitivity
        changes["sensitivity"] = req.sensitivity
    if req.scope is not None:
        doc.scope = req.scope
        changes["scope"] = req.scope

    # Journalisation d'audit
    audit = AuditLog(
        principal_id=admin.id,
        action="update_document",
        target_type="document",
        target_id=doc.id,
        detail=changes
    )
    db.add(audit)
    await db.commit()

    return {"status": "updated", "id": str(doc.id), "changes": changes}


@router.delete("/admin/documents/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID,
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime un document et l'ensemble de ses fragments associés (§14.8)."""
    doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable.")

    doc_title = doc.title
    await db.delete(doc)

    audit = AuditLog(
        principal_id=admin.id,
        action="delete_document",
        target_type="document",
        target_id=doc_id,
        detail={"title": doc_title}
    )
    db.add(audit)
    await db.commit()

    return {"status": "deleted", "id": str(doc_id), "title": doc_title}


# =====================================================================
# 4. GESTION DES WORKSPACES
# =====================================================================
@router.get("/admin/workspaces")
async def list_workspaces(
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la liste de tous les workspaces et leurs statistiques (§14.4)."""
    workspaces = (await db.execute(select(Workspace).order_by(Workspace.name))).scalars().all()

    items = []
    for w in workspaces:
        # Compte des documents rattachés
        doc_count = (await db.execute(
            select(func.count(Document.id))
            .join(CollectionWorkspace, CollectionWorkspace.collection_id == Document.collection_id)
            .where(CollectionWorkspace.workspace_id == w.id)
        )).scalar() or 0

        # Compte des collections
        col_count = (await db.execute(
            select(func.count(CollectionWorkspace.collection_id))
            .where(CollectionWorkspace.workspace_id == w.id)
        )).scalar() or 0

        # Compte des policies
        pol_count = (await db.execute(
            select(func.count(Policy.id)).where(Policy.workspace_id == w.id)
        )).scalar() or 0

        items.append({
            "id": str(w.id),
            "name": w.name,
            "slug": w.slug,
            "domain": w.domain,
            "settings": w.settings or {},
            "documents_count": doc_count,
            "collections_count": col_count,
            "policies_count": pol_count,
            "created_at": w.created_at.isoformat() if w.created_at else None
        })

    return {"total": len(items), "workspaces": items}


@router.post("/admin/workspaces")
async def create_workspace(
    req: WorkspaceCreateRequest,
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Crée un nouvel espace de travail isolé (§14.4)."""
    existing = (await db.execute(select(Workspace).where(Workspace.slug == req.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Le slug '{req.slug}' est déjà utilisé.")

    ws = Workspace(
        name=req.name,
        slug=req.slug,
        domain=req.domain,
        settings=req.settings
    )
    db.add(ws)
    await db.flush()

    # Création d'une collection générale par défaut
    col = Collection(name=f"{req.name} - Général", classification="prive")
    db.add(col)
    await db.flush()
    db.add(CollectionWorkspace(collection_id=col.id, workspace_id=ws.id))

    # Journalisation
    audit = AuditLog(
        principal_id=admin.id,
        action="create_workspace",
        target_type="workspace",
        target_id=ws.id,
        detail={"name": ws.name, "slug": ws.slug}
    )
    db.add(audit)
    await db.commit()

    return {"status": "created", "id": str(ws.id), "slug": ws.slug, "name": ws.name}


@router.patch("/admin/workspaces/{ws_id}")
async def update_workspace(
    ws_id: uuid.UUID,
    req: WorkspaceUpdateRequest,
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Modifie la configuration d'un workspace existant (§14.4)."""
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id))).scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace introuvable.")

    changes: dict[str, Any] = {}
    if req.name is not None:
        ws.name = req.name
        changes["name"] = req.name
    if req.domain is not None:
        ws.domain = req.domain
        changes["domain"] = req.domain
    if req.settings is not None:
        current_settings = dict(ws.settings or {})
        current_settings.update(req.settings)
        ws.settings = current_settings
        changes["settings"] = current_settings

    audit = AuditLog(
        principal_id=admin.id,
        action="update_workspace",
        target_type="workspace",
        target_id=ws.id,
        detail=changes
    )
    db.add(audit)
    await db.commit()

    return {"status": "updated", "id": str(ws.id), "name": ws.name, "domain": ws.domain, "changes": changes}


@router.delete("/admin/workspaces/{ws_id}")
async def delete_workspace(
    ws_id: uuid.UUID,
    delete_documents: bool = Query(False, description="Supprimer également tous les documents exclusifs rattachés à ce workspace"),
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime un workspace et ses liaisons, avec option de suppression des documents exclusifs (§14.4)."""
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id))).scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace introuvable.")

    ws_name = ws.name
    ws_slug = ws.slug

    # 1. Identifier les collections associées à ce workspace
    cols = (await db.execute(
        select(CollectionWorkspace.collection_id).where(CollectionWorkspace.workspace_id == ws_id)
    )).scalars().all()

    exclusive_col_ids: list[uuid.UUID] = []
    shared_col_ids: list[uuid.UUID] = []

    for col_id in cols:
        other_links = (await db.execute(
            select(CollectionWorkspace.workspace_id).where(
                CollectionWorkspace.collection_id == col_id,
                CollectionWorkspace.workspace_id != ws_id
            )
        )).scalars().all()
        if other_links:
            shared_col_ids.append(col_id)
        else:
            exclusive_col_ids.append(col_id)

    deleted_docs_count = 0

    if delete_documents and exclusive_col_ids:
        # Trouver tous les documents des collections exclusives
        docs_to_delete = (await db.execute(
            select(Document.id).where(Document.collection_id.in_(exclusive_col_ids))
        )).scalars().all()

        deleted_docs_count = len(docs_to_delete)

        if docs_to_delete:
            # Rompre les références duplicate_of vers ces documents
            await db.execute(
                update(Document)
                .where(Document.duplicate_of.in_(docs_to_delete))
                .values(duplicate_of=None)
            )

            # Supprimer les documents (les versions et fragments cascaderont en cascade FK / ORM)
            await db.execute(
                delete(Document).where(Document.id.in_(docs_to_delete))
            )

    # 2. Supprimer les liaisons CollectionWorkspace pour ce workspace
    await db.execute(delete(CollectionWorkspace).where(CollectionWorkspace.workspace_id == ws_id))

    # 3. Supprimer les collections exclusives désormais orphelines (et vides de documents)
    for col_id in exclusive_col_ids:
        doc_exists = (await db.execute(select(Document.id).where(Document.collection_id == col_id))).first()
        if not doc_exists:
            await db.execute(delete(Collection).where(Collection.id == col_id))

    # 4. Détacher ou nettoyer les dépendances sur le workspace (AuditLog, Feedback, LlmUsage, AnswerCache)
    await db.execute(update(AuditLog).where(AuditLog.workspace_id == ws_id).values(workspace_id=None))
    await db.execute(update(Feedback).where(Feedback.workspace_id == ws_id).values(workspace_id=None))
    await db.execute(update(LlmUsage).where(LlmUsage.workspace_id == ws_id).values(workspace_id=None))
    await db.execute(delete(AnswerCache).where(AnswerCache.workspace_id == ws_id))

    # 5. Supprimer les policies associées au workspace
    await db.execute(delete(Policy).where(Policy.workspace_id == ws_id))

    # 6. Supprimer le workspace lui-même (sources cascade via relationship)
    await db.delete(ws)

    # 7. Audit log
    audit = AuditLog(
        principal_id=admin.id,
        action="delete_workspace",
        target_type="workspace",
        target_id=ws_id,
        detail={
            "name": ws_name,
            "slug": ws_slug,
            "delete_documents": delete_documents,
            "documents_deleted": deleted_docs_count,
        }
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "deleted",
        "id": str(ws_id),
        "name": ws_name,
        "slug": ws_slug,
        "documents_deleted": deleted_docs_count,
    }


# =====================================================================
# 5. SUPERVISION & SANTÉ DE LA STACK (§14.9)
# =====================================================================
@router.get("/admin/health/all")
async def get_all_services_health(
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Vérifie l'état de santé opérationnel de tous les conteneurs de la stack (§14.9)."""
    return await check_all_services(db=db)


# =====================================================================
# 6. MÉTRIQUES ET COÛTS LLM (§14.10)
# =====================================================================
@router.get("/admin/llm/metrics")
async def get_llm_metrics(
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la synthèse d'utilisation des modèles de langage (§14.10)."""
    total_calls = (await db.execute(select(func.count(LlmUsage.id)))).scalar() or 0
    total_tok_in = (await db.execute(select(func.sum(LlmUsage.tokens_input)))).scalar() or 0
    total_tok_out = (await db.execute(select(func.sum(LlmUsage.tokens_output)))).scalar() or 0
    avg_latency = (await db.execute(select(func.avg(LlmUsage.latency_ms)))).scalar() or 0.0

    # Répartition par modèle
    models_query = select(LlmUsage.model, func.count(LlmUsage.id)).group_by(LlmUsage.model)
    by_model = dict((await db.execute(models_query)).all())

    # Répartition par type de requête (answer, classify, embedding)
    types_query = select(LlmUsage.request_type, func.count(LlmUsage.id)).group_by(LlmUsage.request_type)
    by_type = dict((await db.execute(types_query)).all())

    return {
        "total_calls": total_calls,
        "total_tokens_input": total_tok_in,
        "total_tokens_output": total_tok_out,
        "average_latency_ms": round(float(avg_latency), 1),
        "calls_by_model": by_model,
        "calls_by_request_type": by_type
    }


@router.get("/admin/llm/costs")
async def get_llm_costs(
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne les coûts financiers estimés par jour et par workspace (§14.10)."""
    total_cost = (await db.execute(select(func.sum(LlmUsage.estimated_cost)))).scalar() or Decimal("0.0")

    # Coût par workspace
    cost_ws_query = (
        select(Workspace.slug, func.sum(LlmUsage.estimated_cost))
        .join(Workspace, Workspace.id == LlmUsage.workspace_id, isouter=True)
        .group_by(Workspace.slug)
    )
    by_workspace = {
        (slug or "global"): float(cost or 0.0)
        for slug, cost in (await db.execute(cost_ws_query)).all()
    }

    return {
        "total_estimated_cost_usd": float(total_cost),
        "cost_by_workspace": by_workspace
    }


# =====================================================================
# 7. CACHE INTELLIGENT DE RÉPONSES (§16.9)
# =====================================================================
@router.get("/admin/cache")
async def get_cache_stats(
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne les métriques de rétention et d'efficacité du cache (§16.9)."""
    entry_count = (await db.execute(select(func.count(AnswerCache.id)))).scalar() or 0
    hit_count = (await db.execute(select(func.sum(AnswerCache.hit_count)))).scalar() or 0

    top_questions = (await db.execute(
        select(AnswerCache.question, AnswerCache.hit_count, AnswerCache.created_at)
        .order_by(AnswerCache.hit_count.desc())
        .limit(10)
    )).all()

    return {
        "total_cached_entries": entry_count,
        "total_cache_hits": hit_count,
        "top_cached_questions": [
            {"question": q, "hits": h, "cached_since": dt.isoformat() if dt else None}
            for q, h, dt in top_questions
        ]
    }


def generate_audit_summary(action: str, target_type: Optional[str], detail: dict[str, Any], ws_name: Optional[str]) -> str:
    """Génère un résumé textuel clair et intelligible pour un humain d'après l'audit log."""
    detail = detail or {}
    q = detail.get("query")
    if action == "search":
        count = detail.get("results_count", 0)
        return f"Recherche : « {q} » ({count} résultat{'s' if count > 1 else ''})" if q else f"Recherche de documents ({count} résultat{'s' if count > 1 else ''})"
    elif action == "answer":
        count = detail.get("sources_count", 0)
        conf = detail.get("confidence")
        conf_str = f", confiance {conf}" if conf is not None else ""
        return f"Question RAG : « {q} » ({count} source{'s' if count > 1 else ''}{conf_str})" if q else "Génération de réponse RAG"
    elif action == "delete_workspace":
        ws_n = detail.get("name") or ws_name or "workspace"
        deleted_docs = detail.get("documents_deleted", 0)
        if deleted_docs:
            return f"Suppression du workspace « {ws_n} » ({deleted_docs} document(s) supprimé(s))"
        return f"Suppression du workspace « {ws_n} »"
    elif action == "create_workspace":
        ws_n = detail.get("name") or "workspace"
        return f"Création du workspace « {ws_n} »"
    elif action == "update_workspace":
        ws_n = detail.get("name") or ws_name or "workspace"
        return f"Mise à jour du workspace « {ws_n} »"
    elif action == "validate_document":
        title = detail.get("title") or "document"
        return f"Validation du document « {title} »"
    elif action == "reject_document":
        title = detail.get("title") or "document"
        return f"Rejet du document « {title} »"
    elif action == "delete_document":
        title = detail.get("title") or "document"
        return f"Suppression du document « {title} »"
    elif action == "update_document":
        title = detail.get("title") or "document"
        changes = detail.get("changes", {})
        changes_str = ", ".join(f"{k}→{v}" for k, v in changes.items())
        return f"Modification de « {title} » ({changes_str})" if changes_str else f"Modification de « {title} »"
    elif action == "ingest":
        title = detail.get("title") or "document"
        return f"Indexation du document « {title} »"
    elif action == "export_knowledge_base":
        return f"Export global de la base ({detail.get('documents_count', 0)} documents, {detail.get('fragments_count', 0)} fragments)"
    elif action == "gdpr_anonymization":
        return f"Anonymisation RGPD ({detail.get('fragments_updated', 0)} fragments anonymisés)"

    if q:
        return f"{action} : « {q} »"
    if detail.get("name"):
        return f"{action} sur « {detail['name']} »"
    if detail.get("title"):
        return f"{action} sur « {detail['title']} »"
    return f"Action {action} sur {target_type or 'ressource'}"


# =====================================================================
# 8. AUDIT LOGS (§14.7, Task 3.17)
# =====================================================================
@router.get("/admin/audit", response_model=AuditLogResponse)
async def get_audit_logs(
    workspace_id: Optional[str] = Query(None, description="UUID ou slug du workspace"),
    action: Optional[str] = Query(None, description="Type d'action"),
    principal_id: Optional[str] = Query(None, description="UUID ou external_id du principal"),
    search: Optional[str] = Query(None, description="Recherche textuelle dans les requêtes, détails ou noms"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    """Consulte le journal d'audit enrichi avec pagination et filtres conviviaux (§14.7)."""
    conditions = []

    # Résolution workspace (UUID ou slug)
    if workspace_id:
        try:
            ws_u = uuid.UUID(workspace_id)
            conditions.append(AuditLog.workspace_id == ws_u)
        except (ValueError, TypeError):
            conditions.append(Workspace.slug == workspace_id)

    if action:
        conditions.append(AuditLog.action == action)

    # Résolution principal (UUID ou external_id)
    if principal_id:
        try:
            p_u = uuid.UUID(principal_id)
            conditions.append(AuditLog.principal_id == p_u)
        except (ValueError, TypeError):
            conditions.append(Principal.external_id == principal_id)

    if search:
        search_filter = or_(
            AuditLog.action.ilike(f"%{search}%"),
            cast(AuditLog.detail, String).ilike(f"%{search}%"),
            Principal.external_id.ilike(f"%{search}%"),
            Principal.display_name.ilike(f"%{search}%"),
            Workspace.name.ilike(f"%{search}%"),
            Workspace.slug.ilike(f"%{search}%"),
        )
        conditions.append(search_filter)

    base_query = (
        select(AuditLog, Principal, Workspace)
        .outerjoin(Principal, Principal.id == AuditLog.principal_id)
        .outerjoin(Workspace, Workspace.id == AuditLog.workspace_id)
    )

    count_query = (
        select(func.count(AuditLog.id))
        .outerjoin(Principal, Principal.id == AuditLog.principal_id)
        .outerjoin(Workspace, Workspace.id == AuditLog.workspace_id)
    )

    if conditions:
        base_query = base_query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total = (await db.execute(count_query)).scalar() or 0
    items_stmt = base_query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(items_stmt)).all()

    items = []
    for log, p, ws in rows:
        p_name = p.external_id if p else None
        p_type = p.type if p else ("app" if (p_name and "bot" in p_name.lower()) else "user")
        ws_name = ws.name if ws else None
        ws_slug = ws.slug if ws else None
        detail = log.detail or {}

        summary = generate_audit_summary(log.action, log.target_type, detail, ws_name)
        target_name = None
        if log.target_type == "workspace":
            target_name = ws_name or detail.get("name")
        elif log.target_type == "document":
            target_name = detail.get("title")

        items.append(
            AuditLogItem(
                id=log.id,
                principal_id=log.principal_id,
                principal_name=p_name,
                principal_type=p_type,
                workspace_id=log.workspace_id,
                workspace_name=ws_name,
                workspace_slug=ws_slug,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                target_name=target_name,
                summary=summary,
                detail=detail,
                created_at=log.created_at,
            )
        )

    return AuditLogResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items
    )


# =====================================================================
# 8. EXPORT & PORTABILITÉ GLOBALE (§17 B6)
# =====================================================================
@router.get("/admin/export")
async def export_knowledge_base(
    workspace_id: Optional[uuid.UUID] = Query(None, description="Filtrer par workspace"),
    include_fragments: bool = Query(True, description="Inclure les extraits textuels des fragments"),
    format: str = Query("json", pattern="^(json|download)$"),
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
):
    """
    Exporte l'intégralité ou un sous-ensemble de la base de connaissances (B6).
    Supporte les formats JSON direct et fichier téléchargeable.
    """
    # 1. Workspaces
    ws_query = select(Workspace)
    if workspace_id:
        ws_query = ws_query.where(Workspace.id == workspace_id)
    workspaces = (await db.execute(ws_query)).scalars().all()

    ws_ids = [w.id for w in workspaces]
    if not ws_ids:
        raise HTTPException(status_code=404, detail="Aucun workspace trouvé pour cet export.")

    # 2. Collections
    col_query = (
        select(Collection)
        .join(CollectionWorkspace, Collection.id == CollectionWorkspace.collection_id)
        .where(CollectionWorkspace.workspace_id.in_(ws_ids))
        .distinct()
    )
    collections = (await db.execute(col_query)).scalars().all()
    col_ids = [c.id for c in collections]

    # 3. Documents
    doc_query = (
        select(Document)
        .where(and_(Document.collection_id.in_(col_ids), Document.is_active == True))  # noqa: E712
    )
    documents = (await db.execute(doc_query)).scalars().all()
    doc_ids = [d.id for d in documents]

    # 4. Versions et Fragments
    fragments_by_doc: dict[str, list[dict[str, Any]]] = {}
    total_frags = 0

    if include_fragments and doc_ids:
        frag_query = (
            select(Fragment, DocumentVersion.document_id)
            .join(DocumentVersion, Fragment.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id.in_(doc_ids))
            .order_by(Fragment.chunk_index)
        )
        frag_rows = (await db.execute(frag_query)).all()
        total_frags = len(frag_rows)
        for f, d_id in frag_rows:
            d_key = str(d_id)
            if d_key not in fragments_by_doc:
                fragments_by_doc[d_key] = []
            fragments_by_doc[d_key].append({
                "chunk_index": f.chunk_index,
                "page_number": f.page_number,
                "content": f.content,
                "context_prefix": f.context_prefix,
                "citation_ref": f.citation_ref or {},
            })

    # 5. Policies
    pol_query = select(Policy).where(Policy.workspace_id.in_(ws_ids))
    policies = (await db.execute(pol_query)).scalars().all()

    # Structuration du dump exporté
    export_payload = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": admin.external_id,
        "summary": {
            "workspaces_count": len(workspaces),
            "collections_count": len(collections),
            "documents_count": len(documents),
            "fragments_count": total_frags,
        },
        "workspaces": [
            {
                "id": str(w.id),
                "name": w.name,
                "slug": w.slug,
                "domain": w.domain,
                "description": (w.settings or {}).get("description"),
                "settings": w.settings,
            }
            for w in workspaces
        ],
        "collections": [
            {
                "id": str(c.id),
                "name": c.name,
                "classification": c.classification,
            }
            for c in collections
        ],
        "documents": [
            {
                "id": str(d.id),
                "title": d.title,
                "collection_id": str(d.collection_id),
                "scope": d.scope,
                "sensitivity": d.sensitivity,
                "status": d.status,
                "version": d.version,
                "file_type": (d.metadata_ or {}).get("file_type") or (d.metadata_ or {}).get("extension") or "pdf",
                "sha256": d.content_hash,
                "external_id": (d.metadata_ or {}).get("external_id"),
                "metadata": d.metadata_ or {},
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "fragments": fragments_by_doc.get(str(d.id), []) if include_fragments else None,
            }
            for d in documents
        ],
        "policies": [
            {
                "principal_id": str(p.principal_id),
                "workspace_id": str(p.workspace_id) if p.workspace_id else None,
                "role": p.role,
                "allowed_scopes": p.allowed_scopes,
                "actions": p.actions,
                "max_sensitivity": p.max_sensitivity,
            }
            for p in policies
        ],
    }

    # Journalisation de l'export
    db.add(AuditLog(
        principal_id=admin.id,
        workspace_id=workspaces[0].id if workspaces else None,
        action="export_knowledge_base",
        target_type="system",
        detail={
            "workspaces_count": len(workspaces),
            "documents_count": len(documents),
            "fragments_count": total_frags,
            "format": format,
        }
    ))
    await db.commit()

    if format == "download":
        json_bytes = json.dumps(export_payload, default=str, indent=2, ensure_ascii=False).encode("utf-8")
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"mementomori_export_{timestamp_str}.json"
        return Response(
            content=json_bytes,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return export_payload


# =====================================================================
# 9. RGPD : RÉTENTION DOCUMENTAIRE & ANONYMISATION (§17 B5)
# =====================================================================
class GdprAnonymizeRequest(BaseModel):
    target_pattern: str = Field(..., min_length=2, description="Mot, nom ou identifiant à anonymiser")
    replacement: str = Field("[Donnée personnelle anonymisée]", description="Chaîne de remplacement")
    workspace_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None


@router.get("/admin/gdpr/retention")
async def audit_retention_rules(
    workspace_id: Optional[uuid.UUID] = Query(None, description="Filtrer par workspace"),
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Audit de conformité de rétention documentaire selon les durées légales françaises (§17 B5).
    - Règlements / EDD : conservation permanente
    - PV d'AG : 10 ans (loi 1965)
    - Factures / Comptabilité : 10 ans (Code de commerce)
    - Feuilles de présence : 5 ans
    - Devis / Courriers : 3 ans
    """
    doc_query = select(Document).where(Document.is_active == True)  # noqa: E712
    if workspace_id:
        doc_query = (
            doc_query
            .join(Collection, Document.collection_id == Collection.id)
            .join(CollectionWorkspace, Collection.id == CollectionWorkspace.collection_id)
            .where(CollectionWorkspace.workspace_id == workspace_id)
        )

    docs = (await db.execute(doc_query)).scalars().all()
    now = datetime.now(timezone.utc)

    # Définition des règles légales de rétention
    retention_rules = [
        {"type": "reglement_copro", "label": "Règlements & État descriptif", "legal_years": "permanent"},
        {"type": "pv_ag", "label": "Procès-Verbaux d'Assemblée Générale", "legal_years": 10},
        {"type": "facture", "label": "Factures & Pièces Comptables", "legal_years": 10},
        {"type": "feuille_presence", "label": "Feuilles de présence d'AG", "legal_years": 5},
        {"type": "devis", "label": "Devis et courriers ordinaires", "legal_years": 3},
    ]

    items = []
    eligible_for_archive_count = 0

    for d in docs:
        doc_type = ((d.metadata_ or {}).get("file_type") or "").lower()
        title_lower = (d.title or "").lower()
        created_at = d.created_at or now
        age_days = (now - created_at).days
        age_years = round(age_days / 365.25, 2)

        # Détermination de la durée légale applicable
        if "reglement" in title_lower or "edd" in title_lower:
            rule_type = "reglement_copro"
            limit_years = None
            is_permanent = True
        elif "ag" in title_lower or "assemblee" in title_lower or "pv" in title_lower:
            rule_type = "pv_ag"
            limit_years = 10
            is_permanent = False
        elif "facture" in title_lower or "compta" in title_lower or "grand livre" in title_lower:
            rule_type = "facture"
            limit_years = 10
            is_permanent = False
        elif "presence" in title_lower:
            rule_type = "feuille_presence"
            limit_years = 5
            is_permanent = False
        else:
            rule_type = "devis"
            limit_years = 3
            is_permanent = False

        is_expired = False
        if not is_permanent and limit_years and age_years > limit_years:
            is_expired = True
            eligible_for_archive_count += 1

        items.append({
            "document_id": str(d.id),
            "title": d.title,
            "created_at": created_at.isoformat(),
            "age_years": age_years,
            "rule_type": rule_type,
            "retention_years": "permanent" if is_permanent else limit_years,
            "status": "eligible_archivage" if is_expired else "conforme",
        })

    return {
        "retention_rules": retention_rules,
        "total_documents_checked": len(docs),
        "compliant_count": len(docs) - eligible_for_archive_count,
        "eligible_for_archive_count": eligible_for_archive_count,
        "items": items,
    }


@router.post("/admin/gdpr/anonymize")
async def anonymize_personal_data(
    req: GdprAnonymizeRequest,
    admin: Principal = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Droit à l'effacement et anonymisation de données personnelles (§17 B5).
    Recherche et remplace les occurrences nominatives dans les fragments et purge le cache.
    """
    pattern = req.target_pattern.strip()
    if len(pattern) < 2:
        raise HTTPException(status_code=400, detail="Le motif à anonymiser doit comporter au moins 2 caractères.")

    # 1. Recherche des fragments cibles
    frag_query = select(Fragment).where(Fragment.content.ilike(f"%{pattern}%"))

    if req.document_id:
        frag_query = (
            frag_query
            .join(DocumentVersion, Fragment.document_version_id == DocumentVersion.id)
            .where(DocumentVersion.document_id == req.document_id)
        )
    elif req.workspace_id:
        frag_query = (
            frag_query
            .join(DocumentVersion, Fragment.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .join(Collection, Document.collection_id == Collection.id)
            .join(CollectionWorkspace, Collection.id == CollectionWorkspace.collection_id)
            .where(CollectionWorkspace.workspace_id == req.workspace_id)
        )

    matched_frags = (await db.execute(frag_query)).scalars().all()
    count = len(matched_frags)

    # 2. Remplacement et réindexation
    import re
    compiled_re = re.compile(re.escape(pattern), re.IGNORECASE)

    for frag in matched_frags:
        frag.content = compiled_re.sub(req.replacement, frag.content)
        # Régénération du vecteur textuel PostgreSQL
        frag.search_vector = func.to_tsvector("french", frag.content)

    # 3. Invalidation du cache de réponses
    if req.workspace_id:
        await db.execute(delete(AnswerCache).where(AnswerCache.workspace_id == req.workspace_id))
    else:
        await db.execute(delete(AnswerCache))

    # 4. Traçage dans l'audit log
    db.add(AuditLog(
        principal_id=admin.id,
        workspace_id=req.workspace_id,
        action="gdpr_anonymization",
        target_type="system",
        detail={
            "fragments_updated": count,
            "replacement": req.replacement,
            "document_id": str(req.document_id) if req.document_id else None,
            "workspace_id": str(req.workspace_id) if req.workspace_id else None,
        }
    ))

    await db.commit()

    logger.info("gdpr_anonymization_completed", fragments_count=count, pattern_len=len(pattern))
    return {
        "status": "success",
        "fragments_anonymized": count,
        "cache_cleared": True,
        "replacement": req.replacement,
    }

