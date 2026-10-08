"""Tests d'intégration des endpoints de l'API (Task 3.16)."""

import pytest
import uuid
from sqlalchemy import select
from knowledge.models import Workspace

@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    # 1. Sonde publique : doit masquer les composants internes par défaut (anti-reconnaissance)
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "postgres" not in data
    assert "version" not in data

    # 2. Sonde détaillée : diagnostic interne
    resp_detailed = await async_client.get("/health?detailed=true")
    assert resp_detailed.status_code == 200
    data_detailed = resp_detailed.json()
    assert data_detailed["status"] in ("ok", "degraded")
    assert "postgres" in data_detailed
    assert "redis" in data_detailed

@pytest.mark.asyncio
async def test_unauthorized_search(async_client):
    # Requête sans headers auth
    resp = await async_client.post(
        "/v1/search",
        json={"workspace_id": str(uuid.uuid4()), "query": "test"}
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_docs_protection(async_client):
    # Sans identifiants Basic Auth -> 401
    resp = await async_client.get("/docs")
    assert resp.status_code == 401

    # Avec bons identifiants -> 200
    resp_auth = await async_client.get("/docs", auth=("admin", "mementomori_admin"))
    assert resp_auth.status_code == 200

@pytest.mark.asyncio
async def test_search_and_answer_with_dev_principal(async_client, db_session):
    # Récupérer un workspace
    res = await db_session.execute(select(Workspace).where(Workspace.slug == "copro"))
    ws = res.scalar_one_or_none()
    assert ws is not None
    ws_id = str(ws.id)

    headers = {"X-Dev-Principal": "csbot"}

    # Test Search
    s_resp = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "ascenseur", "top_k": 3},
        headers=headers
    )
    assert s_resp.status_code == 200
    s_data = s_resp.json()
    assert "results" in s_data
    assert s_data["total"] >= 1

    # Test Answer
    a_resp = await async_client.post(
        "/v1/answer",
        json={"workspace_id": ws_id, "query": "ascenseur", "top_k": 3, "use_cache": True},
        headers=headers
    )
    assert a_resp.status_code == 200
    a_data = a_resp.json()
    assert "answer" in a_data
    assert "citations" in a_data
