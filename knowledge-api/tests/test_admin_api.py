"""Tests automatisés pour l'API d'Administration /v1/admin/* (Sprint 8, Task 8.5)."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import Workspace, Collection, CollectionWorkspace, Document, DocumentVersion, Fragment


@pytest.mark.asyncio
async def test_admin_access_control(async_client: AsyncClient):
    """Vérifie que les endpoints admin sont protégés contre les accès non authentifiés ou non-admin."""
    # 1. Sans authentification -> 401
    resp = await async_client.get("/v1/admin/stats")
    assert resp.status_code == 401

    # 2. Utilisateur standard sans droits admin -> 403
    resp_forbidden = await async_client.get(
        "/v1/admin/stats",
        headers={"X-Dev-Principal": "copro_user"}
    )
    assert resp_forbidden.status_code == 403
    assert "Accès refusé" in resp_forbidden.json()["detail"]


@pytest.mark.asyncio
async def test_admin_stats(async_client: AsyncClient):
    """Vérifie le point d'accès synthétique des KPIs plateforme."""
    resp = await async_client.get(
        "/v1/admin/stats",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "workspaces" in data
    assert "documents" in data
    assert "fragments" in data
    assert "pending_validation" in data
    assert "status_distribution" in data
    assert "documents_by_workspace" in data
    assert data["workspaces"] >= 1
    assert data["documents"] >= 1


@pytest.mark.asyncio
async def test_admin_documents_list_and_filters(async_client: AsyncClient):
    """Vérifie la pagination et le filtrage des documents."""
    resp = await async_client.get(
        "/v1/admin/documents?limit=10&offset=0",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["items"]) >= 1

    # Filtrage par statut actif
    resp_filtered = await async_client.get(
        "/v1/admin/documents?status=actif",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_filtered.status_code == 200
    filtered_data = resp_filtered.json()
    for item in filtered_data["items"]:
        assert item["status"] == "actif"


@pytest.mark.asyncio
async def test_admin_document_lifecycle(async_client: AsyncClient, db_session: AsyncSession):
    """Teste le cycle de vie d'un document: création temporaire, consultation détaillée, mise à jour (PATCH), suppression (DELETE)."""
    # 1. Trouver une collection existante
    col = (await db_session.execute(select(Collection).limit(1))).scalar_one()

    # 2. Créer un document temporaire pour le test
    temp_doc = Document(
        collection_id=col.id,
        title="Document Test Admin",
        status="a_verifier",
        sensitivity="interne",
        scope="copro",
        metadata_={"source": "test_admin"}
    )
    db_session.add(temp_doc)
    await db_session.commit()
    await db_session.refresh(temp_doc)

    doc_id = str(temp_doc.id)

    # 3. Créer une version et un fragment
    version = DocumentVersion(
        document_id=temp_doc.id,
        version_number=1,
        original_file_ref="/data/test_admin_doc.pdf",
        extracted_text="Contenu texte extrait du document de test."
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(version)

    fragment = Fragment(
        document_version_id=version.id,
        chunk_index=0,
        content="Contenu de test pour l'administration et validation."
    )
    db_session.add(fragment)
    await db_session.commit()

    # 4. Consulter les détails complets du document
    resp_get = await async_client.get(
        f"/v1/admin/documents/{doc_id}",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_get.status_code == 200
    doc_detail = resp_get.json()
    assert doc_detail["id"] == doc_id
    assert doc_detail["title"] == "Document Test Admin"
    assert doc_detail["status"] == "a_verifier"
    assert len(doc_detail["versions"]) >= 1

    # 5. Mettre à jour le statut (Validation) et la sensibilité via PATCH
    resp_patch = await async_client.patch(
        f"/v1/admin/documents/{doc_id}",
        json={"status": "actif", "sensitivity": "confidentiel"},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_patch.status_code == 200
    updated_data = resp_patch.json()
    assert updated_data["status"] == "updated"
    assert updated_data["changes"]["status"] == "actif"
    assert updated_data["changes"]["sensitivity"] == "confidentiel"

    # 6. Supprimer le document et vérifier la suppression en cascade
    resp_del = await async_client.delete(
        f"/v1/admin/documents/{doc_id}",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "deleted"

    # Vérifier que le document n'existe plus
    resp_get_after = await async_client.get(
        f"/v1/admin/documents/{doc_id}",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_get_after.status_code == 404


@pytest.mark.asyncio
async def test_admin_workspaces_crud(async_client: AsyncClient):
    """Teste la gestion des workspaces via l'API Admin."""
    unique_slug = f"ws-test-{uuid.uuid4().hex[:6]}"

    # 1. Créer un workspace
    resp_create = await async_client.post(
        "/v1/admin/workspaces",
        json={
            "name": "Workspace Test Admin",
            "slug": unique_slug,
            "domain": "pro",
            "settings": {"auto_publish": False}
        },
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_create.status_code == 200
    ws_created = resp_create.json()
    ws_id = ws_created["id"]
    assert ws_created["slug"] == unique_slug

    # 2. Lister les workspaces et vérifier la présence
    resp_list = await async_client.get(
        "/v1/admin/workspaces",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_list.status_code == 200
    workspaces_data = resp_list.json()
    assert any(w["id"] == ws_id for w in workspaces_data["workspaces"])

    # 3. Mettre à jour le workspace
    resp_patch = await async_client.patch(
        f"/v1/admin/workspaces/{ws_id}",
        json={"name": "Workspace Test Admin Updated"},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["name"] == "Workspace Test Admin Updated"

    # 4. Supprimer le workspace de test pour ne pas polluer la base de données
    resp_del = await async_client.delete(
        f"/v1/admin/workspaces/{ws_id}",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "deleted"
    assert resp_del.json()["documents_deleted"] == 0


@pytest.mark.asyncio
async def test_admin_workspace_delete_with_documents(async_client: AsyncClient, db_session: AsyncSession):
    """Teste la suppression d'un workspace avec suppression en cascade de ses documents exclusifs."""
    unique_slug = f"ws-del-test-{uuid.uuid4().hex[:6]}"

    # 1. Créer un workspace
    resp_create = await async_client.post(
        "/v1/admin/workspaces",
        json={"name": "Workspace Del Test", "slug": unique_slug, "domain": "pro"},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_create.status_code == 200
    ws_id = uuid.UUID(resp_create.json()["id"])

    # 2. Créer une collection exclusive rattachée à ce workspace
    col = Collection(name=f"Col Test {unique_slug}", classification="prive")
    db_session.add(col)
    await db_session.commit()
    await db_session.refresh(col)

    cw = CollectionWorkspace(collection_id=col.id, workspace_id=ws_id)
    db_session.add(cw)
    await db_session.commit()

    # 3. Créer un document dans cette collection avec version et fragment
    doc = Document(
        collection_id=col.id,
        title="Document Exclusif A Purger",
        status="actif",
        scope="pro",
        sensitivity="interne"
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    doc_id = doc.id

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        original_file_ref="/data/doc_del_test.pdf",
        extracted_text="Contenu du document à supprimer avec le workspace."
    )
    db_session.add(ver)
    await db_session.commit()
    await db_session.refresh(ver)

    frag = Fragment(
        document_version_id=ver.id,
        chunk_index=0,
        content="Fragment du document à supprimer."
    )
    db_session.add(frag)
    await db_session.commit()

    # 4. Supprimer le workspace avec l'option delete_documents=true
    resp_del = await async_client.delete(
        f"/v1/admin/workspaces/{ws_id}?delete_documents=true",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_del.status_code == 200
    del_data = resp_del.json()
    assert del_data["status"] == "deleted"
    assert del_data["documents_deleted"] == 1

    # 5. Vérifier en base que le workspace, le document, la collection et le fragment sont bien supprimés
    ws_db = (await db_session.execute(select(Workspace).where(Workspace.id == ws_id))).scalar_one_or_none()
    assert ws_db is None

    doc_db = (await db_session.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    assert doc_db is None

    col_db = (await db_session.execute(select(Collection).where(Collection.id == col.id))).scalar_one_or_none()
    assert col_db is None

    frag_db = (await db_session.execute(select(Fragment).where(Fragment.id == frag.id))).scalar_one_or_none()
    assert frag_db is None



@pytest.mark.asyncio
async def test_admin_health_all(async_client: AsyncClient):
    """Vérifie le diagnostic complet de santé de la stack d'infrastructure."""
    resp = await async_client.get(
        "/v1/admin/health/all",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert "postgres" in data["services"]
    assert "redis" in data["services"]
    assert "paperless" in data["services"]
    assert "authentik" in data["services"]
    assert data["services"]["postgres"]["status"] == "ok"
    assert data["services"]["redis"]["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_llm_and_cache_metrics(async_client: AsyncClient):
    """Vérifie la consultation des métriques LLM, des coûts financiers et des statistiques de cache."""
    # 1. Métriques LLM
    resp_llm = await async_client.get(
        "/v1/admin/llm/metrics",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_llm.status_code == 200
    data_llm = resp_llm.json()
    assert "total_calls" in data_llm
    assert "total_tokens_input" in data_llm
    assert "total_tokens_output" in data_llm
    assert "average_latency_ms" in data_llm

    # 2. Coûts LLM
    resp_costs = await async_client.get(
        "/v1/admin/llm/costs",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_costs.status_code == 200
    data_costs = resp_costs.json()
    assert "total_estimated_cost_usd" in data_costs
    assert "cost_by_workspace" in data_costs

    # 3. Statistiques du Cache
    resp_cache = await async_client.get(
        "/v1/admin/cache",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_cache.status_code == 200
    data_cache = resp_cache.json()
    assert "total_cached_entries" in data_cache
    assert "total_cache_hits" in data_cache
    assert "top_cached_questions" in data_cache
