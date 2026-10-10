"""
Tests automatisés du Sprint 14 : Expérience Utilisateur & Assistant Universel Multi-Workspaces.
Vérifie les exigences V35, V36, §8.1, §16.13 et les tâches 14.1 et 14.2.
"""

from __future__ import annotations

import pytest
import uuid
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from knowledge.models import Workspace, Principal, Policy
from knowledge.services.orchestrator import (
    classify_question,
    delegate_to_subagent,
    multi_workspace_search,
    orchestrate_query,
    WORKSPACE_TO_AGENT,
    fallback_classify_by_keywords,
    ClassificationResult,
    WorkspaceMatch
)


@pytest.mark.asyncio
async def test_all_nine_subagents_and_policies_configured(db_session):
    """Vérifie que les 9 sous-agents spécialisés ont leurs politiques RBAC sur leurs workspaces respectifs."""
    expected_workspaces = [
        ("copro", "csbot"),
        ("finances-perso", "agent-finances"),
        ("admin-perso", "agent-admin"),
        ("sante-perso", "agent-sante"),
        ("entreprise", "agent-entreprise"),
        ("dev", "agent-dev"),
        ("formation", "agent-formation"),
        ("consulting", "agent-consulting"),
        ("veille", "agent-veille"),
    ]

    for ws_slug, expected_agent in expected_workspaces:
        # 1. Workspace
        ws = (await db_session.execute(select(Workspace).where(Workspace.slug == ws_slug))).scalar_one_or_none()
        assert ws is not None, f"Workspace manquant : '{ws_slug}'"

        # 2. Agent Principal
        principal = (await db_session.execute(select(Principal).where(Principal.external_id == expected_agent))).scalar_one_or_none()
        assert principal is not None, f"Principal sous-agent manquant : '{expected_agent}' pour '{ws_slug}'"

        # 3. Policy RBAC
        policy = (await db_session.execute(
            select(Policy).where(
                Policy.workspace_id == ws.id,
                Policy.principal_id == principal.id
            )
        )).scalar_one_or_none()
        assert policy is not None, f"Policy manquante pour l'agent '{expected_agent}' sur le workspace '{ws_slug}'"
        assert "read" in policy.actions
        assert "search" in policy.actions


@pytest.mark.asyncio
async def test_fallback_classification_across_all_nine_workspaces(db_session):
    """Vérifie la classification sémantique déterministe sur les 9 workspaces."""
    res = await db_session.execute(select(Workspace))
    workspaces = res.scalars().all()

    test_cases = [
        ("Quels sont les horaires pour les travaux bruyants et le bruit ?", "copro"),
        ("Quel est le solde de mon compte courant fin janvier à la banque ?", "finances-perso"),
        ("Où est rangé mon passeport et mon contrat d'assurance habitation ?", "admin-perso"),
        ("Quels sont les résultats de mes analyses de sang et glycémie ?", "sante-perso"),
        ("Quel est le chiffre d'affaires et la déclaration URSSAF de la société ?", "entreprise"),
        ("Où trouver l'architecture technique microservices et l'API ?", "dev"),
        ("Explique-moi le fonctionnement des mécanismes d'attention Transformer dans ce cours", "formation"),
        ("Quel est le TJM dans la proposition commerciale d'audit ?", "consulting"),
        ("Quelle est la synthèse de conformité pour la directive NIS2 et les LLM ?", "veille"),
    ]

    for question, expected_slug in test_cases:
        res_class = fallback_classify_by_keywords(question, workspaces)
        matched_slugs = [m.workspace_slug for m in res_class.workspaces]
        assert expected_slug in matched_slugs, f"Question '{question}' non classifiée vers '{expected_slug}'. Obtenus: {matched_slugs}"
        assert res_class.strategy in ("single", "multi")


@pytest.mark.asyncio
async def test_cross_workspace_classification_and_search(db_session):
    """Vérifie la détection transversale multi-workspaces (ex: copro + finances pour charges)."""
    res = await db_session.execute(select(Workspace))
    workspaces = res.scalars().all()

    question = "Puis-je payer l'appel de fonds et mes charges avec le solde de mon compte ?"
    res_class = fallback_classify_by_keywords(question, workspaces)
    assert res_class.strategy == "multi"
    matched_slugs = [m.workspace_slug for m in res_class.workspaces]
    assert "copro" in matched_slugs
    assert "finances-perso" in matched_slugs


@pytest.mark.asyncio
async def test_unknown_question_orchestration(async_client):
    """Vérifie que l'orchestrateur gère les questions hors-domaine avec guidance claire."""
    resp = await async_client.post(
        "/v1/orchestrate/query",
        json={"query": "recette tajine poulet aux olives et citrons confits", "top_k": 5},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy"] == "unknown"
    assert "Je n'ai pas trouvé d'espace" in data["answer"]
    assert "copro" in data["answer"]
    assert "finances-perso" in data["answer"]


@pytest.mark.asyncio
async def test_orchestrate_query_endpoint_dev_workspace(async_client):
    """Vérifie l'interrogation universelle /v1/orchestrate/query sur le workspace dev."""
    resp = await async_client.post(
        "/v1/orchestrate/query",
        json={"query": "Quelles sont les conventions de développement et architecture microservices ?", "top_k": 5},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy"] in ("single", "multi")
    if data["strategy"] == "single":
        assert data["workspace"] == "dev"
        assert data["agent"] == "agent-dev"
    assert len(data["answer"]) > 10
    assert "sources" in data


@pytest.mark.asyncio
async def test_orchestrate_classify_endpoint(async_client):
    """Vérifie le point d'entrée /v1/orchestrate/classify (§16.13)."""
    resp = await async_client.post(
        "/v1/orchestrate/classify",
        json={"query": "Comment déclarer mon chiffre d'affaires et cotisations URSSAF ?"},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "strategy" in data
    assert "workspaces" in data
    slugs = [w["slug"] for w in data["workspaces"]]
    assert "entreprise" in slugs

