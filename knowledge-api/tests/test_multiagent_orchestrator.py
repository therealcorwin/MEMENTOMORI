"""
Tests automatisés du Sprint 7 : Architecture Multi-Agents & Orchestrateur Central.
Vérifie les exigences §8, §16.5, §16.13, §16.14 et les tâches 7.1 à 7.9.
"""

from __future__ import annotations

import pytest
import uuid
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from knowledge.models import Workspace, Collection, CollectionWorkspace, Principal, Policy
from knowledge.services.orchestrator import (
    classify_question,
    delegate_to_subagent,
    multi_workspace_search,
    orchestrate_query,
    ClassificationResult,
    WorkspaceMatch
)
from knowledge.services.adaptive_search import (
    evaluate_search_quality,
    adaptive_hybrid_search,
    SearchQuality
)
from knowledge.services.search import SearchResult


@pytest.mark.asyncio
async def test_agent_service_accounts_and_policies_exist(db_session):
    """Tâche 7.1 & 7.2 : Vérifie la présence des service accounts agents et de leurs politiques en base."""
    # 1. Vérification des Principals
    expected_agents = ["csbot", "agent-finances", "agent-sante", "agent-dev", "orchestrator"]
    res = await db_session.execute(
        select(Principal).where(Principal.external_id.in_(expected_agents))
    )
    principals = {p.external_id: p for p in res.scalars().all()}
    for agent_id in expected_agents:
        assert agent_id in principals, f"Service account manquant : {agent_id}"

    # 2. Vérification des Policies
    # agent-finances sur finances-perso
    ws_fin = (await db_session.execute(select(Workspace).where(Workspace.slug == "finances-perso"))).scalar_one_or_none()
    assert ws_fin is not None

    pol_fin = (await db_session.execute(
        select(Policy).where(Policy.workspace_id == ws_fin.id, Policy.principal_id == principals["agent-finances"].id)
    )).scalar_one_or_none()
    assert pol_fin is not None
    assert pol_fin.role == "reader"
    assert "finances" in pol_fin.allowed_scopes
    assert pol_fin.max_sensitivity == "confidentiel"

    # 3. Tâche 7.5 : Vérifier que l'orchestrateur n'a AUCUNE policy directe en base
    orch_policies = (await db_session.execute(
        select(Policy).where(Policy.principal_id == principals["orchestrator"].id)
    )).scalars().all()
    assert len(orch_policies) == 0, "L'orchestrateur ne doit avoir AUCUNE policy directe en base"


@pytest.mark.asyncio
async def test_orchestrator_cannot_access_data_directly(async_client, db_session):
    """Tâche 7.5 : Vérifie que l'orchestrateur est rejeté (403) s'il tente d'interroger /v1/search directement."""
    ws = (await db_session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))).scalar_one_or_none()
    assert ws is not None

    resp = await async_client.post(
        "/v1/search",
        json={"workspace_id": str(ws.id), "query": "Contrat de maintenance", "top_k": 5},
        headers={"X-Dev-Principal": "orchestrator"}
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"].lower()
    assert "refusé" in detail or "policy" in detail or "forbidden" in detail


@pytest.mark.asyncio
async def test_shared_collection_many_to_many(db_session):
    """Tâche 7.7 : Vérifie la liaison many-to-many Collection <-> Workspaces."""
    col = (await db_session.execute(
        select(Collection).where(Collection.name == "Justificatifs & Paiements Transverses")
    )).scalar_one_or_none()
    assert col is not None

    # Doit être rattachée à copro-jardins ET finances-perso
    links = (await db_session.execute(
        select(CollectionWorkspace).where(CollectionWorkspace.collection_id == col.id)
    )).scalars().all()
    assert len(links) >= 2

    ws_ids = {l.workspace_id for l in links}
    ws_copro = (await db_session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))).scalar_one()
    ws_fin = (await db_session.execute(select(Workspace).where(Workspace.slug == "finances-perso"))).scalar_one()

    assert ws_copro.id in ws_ids
    assert ws_fin.id in ws_ids


@pytest.mark.asyncio
async def test_orchestrator_classification_single_workspace(db_session):
    """Tâche 7.3 : Vérifie la classification déterministe pour des questions mono-workspace."""
    # Copropriété
    c_copro = await classify_question("Quels sont les horaires autorisés pour les travaux bruyants ?", db=db_session)
    assert c_copro.strategy == "single"
    assert c_copro.workspaces[0].workspace_slug == "copro-jardins"

    # Finances
    c_fin = await classify_question("Quel est le solde de mon compte courant et de mon livret A ?", db=db_session)
    assert c_fin.strategy == "single"
    assert c_fin.workspaces[0].workspace_slug == "finances-perso"

    # Dev / Infra
    c_dev = await classify_question("Quels ports écoute le conteneur PostgreSQL dans Docker ?", db=db_session)
    assert c_dev.strategy == "single"
    assert c_dev.workspaces[0].workspace_slug == "dev"

    # Hors-domaine
    c_unknown = await classify_question("Recette gâteau au chocolat fondant", db=db_session)
    assert c_unknown.strategy == "unknown"


@pytest.mark.asyncio
async def test_orchestrator_classification_multi_workspace(db_session):
    """Tâche 7.9 : Vérifie la classification transversale multi-workspaces."""
    q = "Ai-je les moyens de payer l'appel de fonds du premier trimestre sur mon solde de compte ?"
    c_multi = await classify_question(q, db=db_session)
    assert c_multi.strategy == "multi"
    slugs = {m.workspace_slug for m in c_multi.workspaces}
    assert "copro-jardins" in slugs
    assert "finances-perso" in slugs


@pytest.mark.asyncio
async def test_orchestrator_delegation_to_subagent(db_session):
    """Tâche 7.4 : Vérifie la délégation transparente d'une question à un sous-agent."""
    # Délégation à l'agent finances
    res = await delegate_to_subagent(
        workspace_slug="finances-perso",
        query="Quel est le montant de mon impôt sur le revenu 2024 ?",
        db=db_session,
        is_answer=True
    )
    assert res["status"] == "success"
    assert res["agent"] == "agent-finances"
    assert res["workspace_slug"] == "finances-perso"
    assert len(res["results"]) > 0
    assert any("Imposition" in r.document_title for r in res["results"])


@pytest.mark.asyncio
async def test_adaptive_search_confidence_and_reformulation(db_session):
    """Tâche 7.8 : Vérifie l'évaluation de qualité et la reformulation adaptative (§16.14, B15)."""
    # 1. Évaluation de la qualité de recherche
    # Résultats vides -> verdict 'empty'
    q_empty = evaluate_search_quality([])
    assert q_empty.verdict == "empty"
    assert q_empty.confidence == 0.0

    # Résultat fictif avec score élevé -> 'good'
    dummy_good = [
        SearchResult(
            fragment_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Titre Test",
            version=1,
            content="Contenu",
            context_prefix=None,
            page_number=1,
            score=0.75,
            citation_ref={},
            sensitivity="interne",
            scope="public"
        )
    ]
    q_good = evaluate_search_quality(dummy_good)
    assert q_good.verdict == "good"
    assert q_good.confidence >= 0.50

    # 2. Test recherche adaptative sur workspace finances-perso
    ws_fin = (await db_session.execute(select(Workspace).where(Workspace.slug == "finances-perso"))).scalar_one()
    results, final_q, quality = await adaptive_hybrid_search(
        query="solde liquide disponible",
        workspace_ids=[ws_fin.id],
        allowed_scopes=["finances", "public"],
        max_sensitivity="confidentiel",
        db=db_session,
        top_k=3,
        max_retries=1
    )
    assert len(results) > 0
    assert quality.confidence > 0.0


@pytest.mark.asyncio
async def test_orchestrate_api_endpoints(async_client):
    """Vérifie les points d'entrée HTTP de l'orchestrateur /v1/orchestrate/*."""
    headers = {"X-Dev-Principal": "admin_user"}

    # 1. POST /v1/orchestrate/classify
    resp_c = await async_client.post(
        "/v1/orchestrate/classify",
        json={"query": "Comment déployer la stack docker ?"},
        headers=headers
    )
    assert resp_c.status_code == 200
    data_c = resp_c.json()
    assert data_c["strategy"] in ("single", "multi")
    assert any(w["slug"] == "dev" for w in data_c["workspaces"])

    # 2. POST /v1/orchestrate/query (mono-workspace)
    resp_q = await async_client.post(
        "/v1/orchestrate/query",
        json={"query": "Quel est le solde de mon compte de dépôt et livret A ?"},
        headers=headers
    )
    assert resp_q.status_code == 200
    data_q = resp_q.json()
    assert data_q["strategy"] in ("single", "multi")
    assert "answer" in data_q

    # 3. POST /v1/orchestrate/query (requête transversale copro + finances)
    resp_multi = await async_client.post(
        "/v1/orchestrate/query",
        json={"query": "Ai-je les moyens de payer l'appel de fonds du premier trimestre ?"},
        headers=headers
    )
    assert resp_multi.status_code == 200
    data_multi = resp_multi.json()
    assert data_multi["strategy"] == "multi"
    assert len(data_multi.get("workspaces", [])) >= 2
    assert "copro-jardins" in data_multi["workspaces"]
    assert "finances-perso" in data_multi["workspaces"]
    assert "answer" in data_multi
    assert len(data_multi.get("sources", [])) > 0
