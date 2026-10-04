"""Router d'ingestion POST /v1/ingest (Task 3.8 & 3.13)."""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.dependencies import get_db, get_current_principal
from knowledge.logging import get_logger
from knowledge.models import Principal
from knowledge.schemas import IngestRequest
from knowledge.services.ingestion import run_paperless_sync

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Ingest"])

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
