from typing import Any, List, Optional
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
from knowledge.services.git_ingest import (
    ingest_git_repository,
    ingest_git_file,
    GitSyncResult,
)
from knowledge.services.markdown_sync import (
    sync_markdown_directory,
    ingest_single_markdown_note,
    MarkdownSyncResult,
)
from knowledge.services.feed_harvester import (
    harvest_remote_feed,
    harvest_feed_content,
    harvest_web_article,
    FeedHarvestResult,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["Ingest"])


class PaperlessWebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: Optional[int] = Field(None, alias="id")
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list[str]] = Field(default_factory=list)
    workspace_slug: str = "copro"
    collection_name: str = "Archives Copropriété"


class GitIngestPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    repo_path: Optional[str] = Field(None, description="Chemin local du dépôt à synchroniser")
    repo_name: Optional[str] = Field(None, description="Nom logique du dépôt")
    branch: Optional[str] = Field(None, description="Branche Git ciblée")
    workspace_slug: str = Field("dev", description="Workspace cible (défaut: dev)")
    collection_name: str = Field("documentation-technique", description="Collection cible")
    # Pour push de fichier unitaire via webhook
    title: Optional[str] = None
    content: Optional[str] = None
    path: Optional[str] = None
    commit_hash: Optional[str] = None


class MarkdownIngestPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vault_path: Optional[str] = Field(None, description="Répertoire d'un coffre Markdown / Obsidian à synchroniser")
    content: Optional[str] = Field(None, description="Contenu texte d'une note unitaire")
    filename: Optional[str] = Field(None, description="Nom de fichier pour note unitaire")
    vault_name: Optional[str] = Field("notes", description="Nom du coffre source")
    default_workspace: str = Field("formation", description="Workspace de repli")
    default_collection: str = Field("notes-personnelles", description="Collection de repli")


class RssIngestPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    feed_url: Optional[str] = Field(None, description="URL du flux RSS/Atom à moissonner")
    xml_content: Optional[str] = Field(None, description="Contenu XML brut du flux (pour injection directe / n8n)")
    feed_name: Optional[str] = Field(None, description="Nom lisible du flux")
    workspace_slug: str = Field("veille", description="Workspace cible (défaut: veille)")
    collection_name: str = Field("flux-rss", description="Collection cible")


class WebArticlePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str = Field(..., description="URL de l'article source")
    title: str = Field(..., description="Titre de l'article")
    content: str = Field(..., description="Contenu textuel de l'article")
    author: Optional[str] = None
    source_name: Optional[str] = "Web"
    workspace_slug: str = Field("veille", description="Workspace cible (défaut: veille)")
    collection_name: str = Field("articles-web", description="Collection cible")


@router.post("/ingest")
async def trigger_ingestion(
    req: IngestRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Déclenche la synchronisation et l'ingestion des documents Paperless."""
    logger.info("trigger_ingestion_requested", by=principal.external_id, workspace=req.workspace_slug)

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


# =====================================================================
# SPRINT 13 : NOUVEAUX ENDPOINTS DE PIPELINE
# =====================================================================

@router.post("/ingest/git")
async def handle_git_ingest(
    payload: GitIngestPayload,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Synchronise la documentation technique depuis un dépôt Git ou fichier poussé (Task 13.1)."""
    # 1. Mode unitaire (push de fichier ou webhook git commit)
    if payload.content and payload.title:
        doc_id = await ingest_git_file(
            title=payload.title,
            content=payload.content,
            rel_path=payload.path or payload.title,
            repo_name=payload.repo_name or "repo",
            db=db,
            branch=payload.branch or "main",
            commit_hash=payload.commit_hash,
            workspace_slug=payload.workspace_slug,
            collection_name=payload.collection_name,
        )
        return {
            "status": "success",
            "mode": "single_file",
            "document_id": str(doc_id) if doc_id else None,
            "workspace": payload.workspace_slug,
            "collection": payload.collection_name,
        }

    # 2. Mode scan de répertoire Git local
    if payload.repo_path:
        res = await ingest_git_repository(
            repo_path=payload.repo_path,
            db=db,
            repo_name=payload.repo_name,
            branch=payload.branch,
            workspace_slug=payload.workspace_slug,
            collection_name=payload.collection_name,
        )
        return {
            "status": "success",
            "mode": "repo_scan",
            "repo_name": res.repo_name,
            "scanned": res.scanned_files,
            "ingested": res.ingested_count,
            "skipped": res.skipped_count,
            "errors": res.errors,
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Veuillez spécifier 'repo_path' pour scanner un dépôt ou ('title' et 'content') pour un fichier unitaire."
    )


@router.post("/ingest/markdown")
async def handle_markdown_ingest(
    payload: MarkdownIngestPayload,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Synchronise un coffre de notes Markdown/Obsidian ou ingère une note unitaire (Task 13.2)."""
    # 1. Mode note unitaire
    if payload.content:
        fname = payload.filename or "note.md"
        doc_id = await ingest_single_markdown_note(
            content=payload.content,
            filename=fname,
            db=db,
            vault_name=payload.vault_name or "notes",
            default_workspace=payload.default_workspace,
            default_collection=payload.default_collection,
        )
        return {
            "status": "success",
            "mode": "single_note",
            "document_id": str(doc_id) if doc_id else None,
            "filename": fname,
        }

    # 2. Mode coffre complet
    if payload.vault_path:
        res = await sync_markdown_directory(
            directory_path=payload.vault_path,
            db=db,
            default_workspace=payload.default_workspace,
            default_collection=payload.default_collection,
        )
        return {
            "status": "success",
            "mode": "vault_scan",
            "vault_path": res.vault_path,
            "scanned": res.scanned_notes,
            "ingested": res.ingested_count,
            "skipped": res.skipped_count,
            "errors": res.errors,
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Veuillez spécifier 'vault_path' pour scanner un coffre ou 'content' pour une note unitaire."
    )


@router.post("/ingest/rss")
async def handle_rss_ingest(
    payload: RssIngestPayload,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Moissonne un flux RSS/Atom et injecte les articles dans le sas 'a_verifier' (Task 13.3, Règle P5)."""
    if payload.xml_content:
        res = await harvest_feed_content(
            xml_content=payload.xml_content,
            db=db,
            feed_name=payload.feed_name or "Flux XML",
            workspace_slug=payload.workspace_slug,
            collection_name=payload.collection_name,
        )
        return {
            "status": "success",
            "mode": "xml_content",
            "feed_name": res.feed_name,
            "scanned": res.scanned_entries,
            "ingested_pending_validation": res.ingested_count,
            "skipped": res.skipped_count,
            "errors": res.errors,
            "rule_p5_applied": "Documents en statut 'a_verifier' (sas de validation)",
        }

    if payload.feed_url:
        res = await harvest_remote_feed(
            feed_url=payload.feed_url,
            db=db,
            feed_name=payload.feed_name,
            workspace_slug=payload.workspace_slug,
            collection_name=payload.collection_name,
        )
        return {
            "status": "success",
            "mode": "remote_url",
            "feed_name": res.feed_name,
            "scanned": res.scanned_entries,
            "ingested_pending_validation": res.ingested_count,
            "skipped": res.skipped_count,
            "errors": res.errors,
            "rule_p5_applied": "Documents en statut 'a_verifier' (sas de validation)",
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Veuillez spécifier 'feed_url' pour interroger un flux distant ou 'xml_content' pour du XML brut."
    )


@router.post("/ingest/web-article")
async def handle_web_article_ingest(
    payload: WebArticlePayload,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingère un article web moissonné dans le sas 'a_verifier' (Task 13.3, Règle P5)."""
    doc_id = await harvest_web_article(
        url=payload.url,
        title=payload.title,
        text_content=payload.content,
        db=db,
        author=payload.author,
        source_name=payload.source_name or "Web",
        workspace_slug=payload.workspace_slug,
        collection_name=payload.collection_name,
    )
    return {
        "status": "success",
        "document_id": str(doc_id) if doc_id else None,
        "title": payload.title,
        "workspace": payload.workspace_slug,
        "rule_p5_applied": "Document en statut 'a_verifier' (sas de validation)",
    }
