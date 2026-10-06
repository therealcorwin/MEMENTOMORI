"""Tests de validation des fonctionnalités d'Export (B6) et RGPD (B5)."""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import (
    Workspace,
    Collection,
    CollectionWorkspace,
    Document,
    DocumentVersion,
    Fragment,
)


@pytest.mark.asyncio
async def test_admin_export_knowledge_base(async_client: AsyncClient, db_session: AsyncSession):
    headers = {"X-Dev-Principal": "admin_user"}

    # 1. Export standard format JSON
    resp = await async_client.get("/v1/admin/export", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["version"] == "1.0"
    assert "summary" in data
    assert "workspaces" in data
    assert "collections" in data
    assert "documents" in data
    assert data["summary"]["workspaces_count"] >= 1

    # 2. Export format fichier téléchargeable
    resp_dl = await async_client.get("/v1/admin/export?format=download", headers=headers)
    assert resp_dl.status_code == 200
    assert "attachment; filename=mementomori_export_" in resp_dl.headers.get("content-disposition", "")
    assert resp_dl.headers.get("content-type") == "application/json"


@pytest.mark.asyncio
async def test_admin_gdpr_retention_audit(async_client: AsyncClient):
    headers = {"X-Dev-Principal": "admin_user"}

    resp = await async_client.get("/v1/admin/gdpr/retention", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "retention_rules" in data
    assert "total_documents_checked" in data
    assert "compliant_count" in data
    assert "items" in data
    assert len(data["retention_rules"]) >= 4


@pytest.mark.asyncio
async def test_admin_gdpr_anonymization(async_client: AsyncClient, db_session: AsyncSession):
    headers = {"X-Dev-Principal": "admin_user"}

    # Création d'un document avec fragment contenant une donnée personnelle
    ws = Workspace(name="WS GDPR", slug=f"ws-gdpr-{uuid.uuid4().hex[:6]}", domain="pro")
    col = Collection(name="Col GDPR")
    db_session.add_all([ws, col])
    await db_session.flush()

    db_session.add(CollectionWorkspace(collection_id=col.id, workspace_id=ws.id))
    doc = Document(
        collection_id=col.id,
        title="Document Nominatif",
        scope="copro",
        sensitivity="interne",
        version=1,
    )
    db_session.add(doc)
    await db_session.flush()

    doc_ver = DocumentVersion(document_id=doc.id, version_number=1)
    db_session.add(doc_ver)
    await db_session.flush()

    frag = Fragment(
        document_version_id=doc_ver.id,
        chunk_index=0,
        content="Le copropriétaire M. Jean Dupont a réglé la somme de 450 euros.",
        page_number=1,
    )
    db_session.add(frag)
    await db_session.commit()

    # Appel d'anonymisation
    resp = await async_client.post(
        "/v1/admin/gdpr/anonymize",
        json={
            "target_pattern": "M. Jean Dupont",
            "replacement": "[Copropriétaire anonymisé]",
            "workspace_id": str(ws.id),
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["fragments_anonymized"] >= 1
    assert data["cache_cleared"] is True

    # Vérification que le fragment en base est bien anonymisé
    frag_id = frag.id
    res = await db_session.execute(
        select(Fragment.content).execution_options(populate_existing=True).where(Fragment.id == frag_id)
    )
    content = res.scalar_one()
    assert "[Copropriétaire anonymisé]" in content
    assert "M. Jean Dupont" not in content
