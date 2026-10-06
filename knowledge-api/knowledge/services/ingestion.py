"""Pipeline d'ingestion documentaire : Paperless-ngx -> déduplication -> chunking -> embeddings -> PostgreSQL (Task 3.8)."""

import uuid
from typing import Any, List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.config import settings
from knowledge.logging import get_logger
from knowledge.models import (
    Workspace,
    Collection,
    CollectionWorkspace,
    Source,
    Document,
    DocumentVersion,
    Fragment,
    AuditLog,
)
from knowledge.services.chunking import split_into_chunks
from knowledge.services.dedup import check_duplicate, compute_content_hash
from knowledge.services.embedding import generate_embeddings

logger = get_logger(__name__)

async def fetch_paperless_documents(limit: int = 100) -> List[dict[str, Any]]:
    """Récupère les documents indexés depuis l'API REST de Paperless-ngx."""
    url = f"{settings.PAPERLESS_URL.rstrip('/')}/api/documents/?page_size={limit}"
    headers = {"Authorization": f"Token {settings.PAPERLESS_API_TOKEN}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.error("paperless_api_error", status=resp.status_code, body=resp.text)
            return []
        data = resp.json()
        return data.get("results", [])


async def fetch_single_paperless_document(document_id: int) -> Optional[dict[str, Any]]:
    """Récupère les détails et le contenu OCR d'un document unique depuis Paperless-ngx."""
    url = f"{settings.PAPERLESS_URL.rstrip('/')}/api/documents/{document_id}/"
    headers = {"Authorization": f"Token {settings.PAPERLESS_API_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.error("paperless_fetch_single_error", error=str(e), doc_id=document_id)
    return None


async def ingest_single_document(
    title: str,
    content: str,
    workspace_slug: str,
    collection_name: str,
    db: AsyncSession,
    source_type: str = "paperless",
    scope: str = "copro",
    sensitivity: str = "interne",
    original_ref: Optional[str] = None,
    metadata_: Optional[dict[str, Any]] = None,
) -> Optional[uuid.UUID]:
    """Ingère un document unique à travers tout le pipeline de connaissance."""
    if not content or not content.strip():
        logger.warning("skipping_empty_document", title=title)
        return None

    # 1. Résolution ou création du Workspace
    ws_res = await db.execute(select(Workspace).where(Workspace.slug == workspace_slug))
    workspace = ws_res.scalar_one_or_none()
    if not workspace:
        workspace = Workspace(name=workspace_slug.capitalize(), slug=workspace_slug, domain="pro")
        db.add(workspace)
        await db.flush()

    # 2. Résolution ou création de la Collection
    col_res = await db.execute(select(Collection).where(Collection.name == collection_name))
    collection = col_res.scalar_one_or_none()
    if not collection:
        collection = Collection(name=collection_name, classification="partage")
        db.add(collection)
        await db.flush()

        # Liaison Collection <-> Workspace
        link = CollectionWorkspace(collection_id=collection.id, workspace_id=workspace.id)
        db.add(link)
        await db.flush()

    # 3. Résolution ou création de la Source
    src_res = await db.execute(
        select(Source).where(
            Source.workspace_id == workspace.id,
            Source.connector_type == source_type
        )
    )
    source = src_res.scalar_one_or_none()
    if not source:
        source = Source(workspace_id=workspace.id, connector_type=source_type, auto_approve=True)
        db.add(source)
        await db.flush()

    # 4. Vérification Déduplication SHA-256 (§16.4)
    is_dup, dup_id, reason = await check_duplicate(
        content=content,
        db=db,
        source_id=source.id,
        collection_id=collection.id
    )
    if is_dup:
        logger.info("document_deduplicated_skipped", title=title, reason=reason, dup_of=str(dup_id))
        return dup_id

    # 5. Création du Document et de sa DocumentVersion
    content_hash = compute_content_hash(content)
    doc = Document(
        collection_id=collection.id,
        source_id=source.id,
        title=title,
        status="actif",
        scope=scope,
        sensitivity=sensitivity,
        content_hash=content_hash,
        is_active=True,
        version=1,
        metadata_=metadata_ or {}
    )
    db.add(doc)
    await db.flush()

    doc_version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        original_file_ref=original_ref,
        extracted_text=content
    )
    db.add(doc_version)
    await db.flush()

    # 6. Chunking hybride (§16.1)
    chunks = split_into_chunks(
        text=content,
        document_title=title,
        workspace_slug=workspace_slug
    )
    if not chunks:
        logger.warning("no_chunks_generated", title=title)
        return doc.id

    # 7. Calcul des Embeddings vectoriels (768 dimensions)
    # Préparer le texte à vectoriser (avec le préfixe de contexte !)
    texts_to_embed = [f"{c.context_prefix}\n{c.content}" for c in chunks]
    embeddings = await generate_embeddings(texts_to_embed)

    # 8. Insertion des fragments
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        frag = Fragment(
            document_version_id=doc_version.id,
            chunk_index=idx,
            page_number=chunk.page_number,
            content=chunk.content,
            embedding=emb,
            citation_ref={
                "doc_title": title,
                "section": chunk.context_prefix,
                "position": idx
            },
            context_prefix=chunk.context_prefix
        )
        db.add(frag)

    # 9. Journal d'audit
    audit = AuditLog(
        workspace_id=workspace.id,
        action="ingest_document",
        target_type="document",
        target_id=doc.id,
        detail={"title": title, "chunks_count": len(chunks), "hash": content_hash}
    )
    db.add(audit)

    await db.commit()
    logger.info("document_ingested_successfully", doc_id=str(doc.id), title=title, chunks=len(chunks))
    return doc.id


async def run_paperless_sync(
    workspace_slug: str = "copro",
    collection_name: str = "Archives Copropriété",
    db: Optional[AsyncSession] = None
) -> int:
    """Synchronise tous les documents Paperless-ngx dans la base de connaissance."""
    docs = await fetch_paperless_documents()
    logger.info("fetched_documents_from_paperless", count=len(docs))

    total_ingested = 0
    from knowledge.dependencies import async_session_maker

    async def _process_docs(session: AsyncSession) -> int:
        count = 0
        for p_doc in docs:
            title = p_doc.get("title") or "Document sans titre"
            content = p_doc.get("content") or ""
            original_ref = f"paperless://{p_doc.get('id')}"

            # Détermination de la sensibilité et du scope selon tags
            scope = "copro"
            sensitivity = "interne"
            tags = p_doc.get("tags") or []
            # tag 14 = "scope:copro", 15 = "scope:conseil_syndical"
            if 15 in tags:
                scope = "conseil_syndical"
            if 10 in tags:  # public
                sensitivity = "public"

            doc_id = await ingest_single_document(
                title=title,
                content=content,
                workspace_slug=workspace_slug,
                collection_name=collection_name,
                db=session,
                source_type="paperless",
                scope=scope,
                sensitivity=sensitivity,
                original_ref=original_ref,
                metadata_={
                    "paperless_id": p_doc.get("id"),
                    "created": p_doc.get("created"),
                    "doc_type": p_doc.get("document_type")
                }
            )
            if doc_id:
                count += 1
        return count

    if db:
        return await _process_docs(db)
    else:
        async with async_session_maker() as session:
            return await _process_docs(session)
