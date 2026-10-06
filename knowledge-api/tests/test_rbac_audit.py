"""
Tests automatisés du Sprint 5 : RBAC, Sensibilité, Isolation & Audit Trail.
Vérifie les exigences 5.1 à 5.6 du document d'architecture.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from sqlalchemy import select

from knowledge.config import settings
from knowledge.models import Workspace, Principal, Policy
from knowledge.services.llm_resilience import (
    answer_with_fallback,
    FallbackLevel,
    BaseLLMProvider
)

@pytest.mark.asyncio
async def test_rbac_three_roles_different_results(async_client, db_session):
    """
    Tâche 5.1 & 5.5 : Vérifie que les 3 rôles (Copropriétaire, CS, Admin)
    obtiennent des résultats strictement cloisonnés par scope et sensibilité.
    """
    res = await db_session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))
    ws = res.scalar_one_or_none()
    assert ws is not None
    ws_id = str(ws.id)

    # 1. Requête par un Copropriétaire lambda (scopes: public, copro ; max_sens: interne)
    # Cherche le contrat d'ascenseur (scope: conseil_syndical) -> Ne doit PAS le voir !
    resp_copro = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "OTIS maintenance contrat ascenseur 2026", "top_k": 5},
        headers={"X-Dev-Principal": "copro_user"}
    )
    assert resp_copro.status_code == 200
    data_copro = resp_copro.json()
    titles_copro = [r["document_title"] for r in data_copro["results"]]
    assert "Contrat de maintenance ascenseur OTIS 2026" not in titles_copro
    assert "Facture Entretien Espaces Verts - Vert Avenir T1 2026" not in titles_copro

    # 2. Requête par un membre du Conseil Syndical (scopes: public, copro, conseil_syndical ; max_sens: confidentiel)
    # Doit voir le contrat d'ascenseur et la facture espaces verts !
    resp_cs = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "OTIS maintenance contrat ascenseur 2026", "top_k": 10},
        headers={"X-Dev-Principal": "cs_user"}
    )
    assert resp_cs.status_code == 200
    data_cs = resp_cs.json()
    titles_cs = [r["document_title"] for r in data_cs["results"]]
    assert "Contrat de maintenance ascenseur OTIS 2026" in titles_cs

    # Mais le membre CS ne doit PAS voir les documents 'secret' (scope: syndic, sens: secret)
    resp_cs_secret = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "Code alarme sous-sol coffre", "top_k": 5},
        headers={"X-Dev-Principal": "cs_user"}
    )
    assert resp_cs_secret.status_code == 200
    titles_cs_secret = [r["document_title"] for r in resp_cs_secret.json()["results"]]
    assert "Codes d'accès et alarmes sécurisées" not in titles_cs_secret

    # 3. Requête par l'Administrateur (Syndic) (scopes: tous ; max_sens: secret)
    # Doit voir le document secret !
    resp_admin = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "Code alarme sous-sol coffre", "top_k": 5},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_admin.status_code == 200
    titles_admin = [r["document_title"] for r in resp_admin.json()["results"]]
    assert "Codes d'accès et alarmes sécurisées" in titles_admin


@pytest.mark.asyncio
async def test_rbac_lot_isolation(async_client, db_session):
    """
    Tâche 5.6 : Vérifie le cloisonnement granulaire par lot privatif (lot:42).
    """
    res = await db_session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))
    ws = res.scalar_one_or_none()
    ws_id = str(ws.id)

    # 1. Copropriétaire standard (sans scope lot:42)
    resp_standard = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "Alexandre Garcia décompte individuel de charges", "top_k": 5},
        headers={"X-Dev-Principal": "copro_user"}
    )
    assert resp_standard.status_code == 200
    titles_std = [r["document_title"] for r in resp_standard.json()["results"]]
    assert "Décompte individuel de charges 2025 - Lot 42" not in titles_std

    # 2. Copropriétaire titulaire du Lot 42 (avec scope lot:42)
    resp_lot42 = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "Alexandre Garcia décompte individuel de charges", "top_k": 5},
        headers={"X-Dev-Principal": "copro_user_lot42"}
    )
    assert resp_lot42.status_code == 200
    titles_lot42 = [r["document_title"] for r in resp_lot42.json()["results"]]
    assert "Décompte individuel de charges 2025 - Lot 42" in titles_lot42


@pytest.mark.asyncio
async def test_inter_workspace_isolation(async_client, db_session):
    """
    Tâche 5.6 : Vérifie l'isolation stricte inter-workspaces.
    Aucun utilisateur de copro ne peut interroger sante-perso (403 Forbidden).
    """
    res_copro = await db_session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))
    ws_copro = res_copro.scalar_one_or_none()
    assert ws_copro is not None

    res_sante = await db_session.execute(select(Workspace).where(Workspace.slug == "sante-perso"))
    ws_sante = res_sante.scalar_one_or_none()
    assert ws_sante is not None
    sante_id = str(ws_sante.id)

    # 1. copro_user tente d'accéder à sante-perso -> 403 Forbidden
    resp1 = await async_client.post(
        "/v1/search",
        json={"workspace_id": sante_id, "query": "glycémie bilan sanguin"},
        headers={"X-Dev-Principal": "copro_user"}
    )
    assert resp1.status_code == 403
    assert "Accès refusé" in resp1.json()["detail"]

    # 2. admin_user de copro tente d'accéder à sante-perso -> 403 Forbidden (admin n'est pas global)
    resp2 = await async_client.post(
        "/v1/search",
        json={"workspace_id": sante_id, "query": "glycémie bilan sanguin"},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp2.status_code == 403

    # 3. sante_user accède à sante-perso -> 200 OK
    resp3 = await async_client.post(
        "/v1/search",
        json={"workspace_id": sante_id, "query": "glycémie bilan sanguin"},
        headers={"X-Dev-Principal": "sante_user"}
    )
    assert resp3.status_code == 200
    titles_sante = [r["document_title"] for r in resp3.json()["results"]]
    assert "Bilan Sanguin Annuel 2026" in titles_sante

    # 4. sante_user tente d'accéder à copro-jardins -> 403 Forbidden
    resp4 = await async_client.post(
        "/v1/search",
        json={"workspace_id": str(ws_copro.id), "query": "règlement"},
        headers={"X-Dev-Principal": "sante_user"}
    )
    assert resp4.status_code == 403


@pytest.mark.asyncio
async def test_secret_fragment_cloud_leak_prevention(async_client, db_session):
    """
    Tâche 5.3 : Vérifie l'interdiction absolue d'envoyer des fragments 'secret' vers un LLM Cloud.
    """
    # 1. Test unitaire du service de résilience LLM
    class MockFragment:
        def __init__(self, sensitivity: str, content: str, title: str):
            self.sensitivity = sensitivity
            self.content = content
            self.document_title = title

    secret_frags = [
        MockFragment("secret", "Code alarme sous-sol : 9876", "Alarmes"),
        MockFragment("public", "Reglement copro article 1", "Reglement")
    ]

    # Simuler la présence d'une clé API Gemini
    with patch.object(settings, "GEMINI_API_KEY", "fake_cloud_key"):
        with patch.object(settings, "MISTRAL_API_KEY", "fake_mistral_key"):
            resp = await answer_with_fallback(
                system_prompt="Tu es un assistant",
                user_query="Quel est le code alarme ?",
                fragments=secret_frags,
                search_scores=[0.9, 0.5]
            )

            # Le provider NE DOIT PAS être gemini ni mistral
            assert resp.provider not in ("gemini", "mistral")
            # Le niveau de fallback doit être SEARCH_ONLY ou LOCAL
            assert resp.fallback_level in (FallbackLevel.SEARCH_ONLY, FallbackLevel.LOCAL)
            assert "9876" in resp.answer

    # 2. Test d'intégration API : /v1/answer avec admin_user sur le document secret
    res = await db_session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))
    ws_id = str(res.scalar_one_or_none().id)

    ans_resp = await async_client.post(
        "/v1/answer",
        json={
            "workspace_id": ws_id,
            "query": "Quel est le code de l'alarme du sous-sol et la clef ?",
            "use_cache": False
        },
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert ans_resp.status_code == 200
    ans_data = ans_resp.json()
    assert ans_data["provider"] not in ("gemini", "mistral")
    assert any("Codes d'accès" in c for c in ans_data["citations"])


@pytest.mark.asyncio
async def test_audit_log_recording_and_endpoint(async_client, db_session):
    """
    Tâche 5.4 : Vérifie que les actions (search, answer) sont bien enregistrées
    dans audit_log et consultables via GET /v1/admin/audit avec contrôle RBAC.
    """
    res = await db_session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))
    ws_id = str(res.scalar_one_or_none().id)

    # 1. Effectuer une recherche avec admin_user
    trace_test_id = f"trace-audit-test-{uuid.uuid4().hex[:8]}"
    s_resp = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "ascenseur", "trace_id": trace_test_id},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert s_resp.status_code == 200

    # 2. Consulter l'audit trail avec admin_user -> 200 OK
    audit_resp = await async_client.get(
        f"/v1/admin/audit?workspace_id={ws_id}&action=search&limit=10",
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["total"] >= 1
    assert len(audit_data["items"]) >= 1

    # Vérifier la présence du trace_id dans le détail du journal
    matching = [it for it in audit_data["items"] if it.get("detail", {}).get("trace_id") == trace_test_id]
    assert len(matching) == 1
    assert matching[0]["action"] == "search"
    assert matching[0]["workspace_id"] == ws_id

    # 3. Tenter de consulter l'audit trail avec copro_user (non-admin) -> 403 Forbidden
    forbidden_resp = await async_client.get(
        f"/v1/admin/audit?workspace_id={ws_id}",
        headers={"X-Dev-Principal": "copro_user"}
    )
    assert forbidden_resp.status_code == 403
    assert "Accès refusé" in forbidden_resp.json()["detail"]
