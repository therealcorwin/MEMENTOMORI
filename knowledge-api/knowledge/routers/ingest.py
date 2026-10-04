from typing import Any, Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.dependencies import get_db, get_current_principal
from knowledge.logging import get_logger
from knowledge.models import Principal
from knowledge.schemas import IngestRequest
from knowledge.services.ingestion import (
    run_paperless_sync,
    fetch_single_paperless_document,
    ingest_single_document
)

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Ingest"])


class PaperlessWebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: Optional[int] = Field(None, alias="id")
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list[str]] = Field(default_factory=list)
    workspace_slug: str = "copro-jardins"
    collection_name: str = "Archives Copropriété"


@router.post("/ingest")
async def trigger_ingestion(
    req: IngestRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Déclenche la synchronisation et l'ingestion des documents Paperless."""
    logger.info("trigger_ingestion_requested", by=principal.external_id, workspace=req.workspace_slug)

    # Ingestion synchrone si petit lot ou tâche de fond
    count = await run_paperless_sync(
        workspace_slug=req.workspace_slug,
        collection_name=req.collection_name,
        db=db
    )

    return {
        "status": "success",
        "workspace_slug": req.workspace_slug,
        "collection_name": req.collection_name,
        "documents_ingested": count
    }


@router.post("/ingest/paperless-webhook")
async def handle_paperless_webhook(
    payload: PaperlessWebhookPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reçoit les notifications d'ingestion de Paperless-ngx et traite le document (§16.10, Task 6.6)."""
    doc_id = payload.document_id
    title = payload.title
    content = payload.content
    tags = payload.tags or []

    # Si seul l'identifiant est fourni, récupérer les détails via l'API Paperless
    if doc_id and (not content or not title):
        p_doc = await fetch_single_paperless_document(doc_id)
        if p_doc:
            title = p_doc.get("title") or f"Document Paperless #{doc_id}"
            content = p_doc.get("content") or ""
            raw_tags = p_doc.get("tags") or []
            tags = [str(t) for t in raw_tags]

    if not content or not content.strip():
        return {
            "status": "skipped",
            "reason": "empty_content_or_fetch_failed",
            "document_id": doc_id
        }

    # Détection scope et sensibilité depuis les tags ou métadonnées
    scope = "copro"
    sensitivity = "interne"

    for t in tags:
        t_lower = str(t).lower()
        if "cs" in t_lower or "conseil_syndical" in t_lower:
            scope = "conseil_syndical"
        elif "syndic" in t_lower or "owner" in t_lower:
            scope = "syndic"
        elif "public" in t_lower:
            sensitivity = "public"
        elif "secret" in t_lower:
            sensitivity = "secret"
        elif "confidentiel" in t_lower:
            sensitivity = "confidentiel"

    ingested_id = await ingest_single_document(
        title=title or f"Document #{doc_id}",
        content=content,
        workspace_slug=payload.workspace_slug,
        collection_name=payload.collection_name,
        db=db,
        source_type="paperless_webhook",
        scope=scope,
        sensitivity=sensitivity,
        original_ref=f"paperless://{doc_id}" if doc_id else None,
        metadata_={"paperless_id": doc_id, "tags": tags}
    )

    return {
        "status": "ingested",
        "document_id": str(ingested_id),
        "title": title,
        "scope": scope,
        "sensitivity": sensitivity
    }
