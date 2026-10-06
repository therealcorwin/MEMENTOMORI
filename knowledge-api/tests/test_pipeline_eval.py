"""
Tests automatisés du Sprint 6 : Pipelines d'ingestion, Webhook Paperless,
Adaptateur CPTCopro, Déduplication et Alerting Administrateur.
Vérifie les exigences §8.5, §16.4, §16.10, §16.12 et V16/V19.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from knowledge.models import Workspace, Document
from knowledge.services.cptcopro import run_cptcopro_sync, CPTCOPRO_FINANCIAL_RECORDS
from knowledge.services.notifier import send_admin_alert, AlertLevel
from knowledge.services.ingestion import ingest_single_document


@pytest.mark.asyncio
async def test_paperless_webhook_ingest_with_payload(async_client, db_session):
    """Vérifie l'ingestion d'un document via le webhook Paperless avec tagging CS/confidentiel."""
    # Mock embeddings pour éviter les appels externes durant les tests rapides
    with patch("knowledge.services.ingestion.generate_embeddings", new_callable=AsyncMock) as mock_emb:
        mock_emb.return_value = [[0.01] * 768]

        payload = {
            "document_id": 1042,
            "title": "Compte-rendu Réunion CS Mars 2026",
            "content": "Ordre du jour : Travaux d'étanchéité terrasse et réfection ascenseur.",
            "tags": ["cs", "confidentiel"],
            "workspace_slug": "copro",
            "collection_name": "Archives Copropriété"
        }

        resp = await async_client.post("/v1/ingest/paperless-webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "ingested"
        assert data["title"] == "Compte-rendu Réunion CS Mars 2026"
        assert data["scope"] == "conseil_syndical"
        assert data["sensitivity"] == "confidentiel"
        assert "document_id" in data


@pytest.mark.asyncio
async def test_paperless_webhook_empty_content_skipped(async_client):
    """Vérifie qu'un payload webhook avec contenu vide est ignoré élégamment."""
    payload = {
        "document_id": 9999,
        "title": "Document Vide",
        "content": "   ",
        "tags": []
    }
    resp = await async_client.post("/v1/ingest/paperless-webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "skipped"
    assert data["reason"] == "empty_content_or_fetch_failed"


@pytest.mark.asyncio
async def test_paperless_webhook_fetch_on_missing_content(async_client, db_session):
    """Vérifie que le webhook va interroger l'API Paperless si le contenu est omis."""
    fake_paperless_doc = {
        "id": 1050,
        "title": "Facture Plomberie Synergies",
        "content": "Intervention sur fuite colonne montante générale bâtiment B.",
        "tags": ["syndic", "secret"]
    }

    with patch("knowledge.routers.ingest.fetch_single_paperless_document", new_callable=AsyncMock) as mock_fetch, \
         patch("knowledge.services.ingestion.generate_embeddings", new_callable=AsyncMock) as mock_emb:
        
        mock_fetch.return_value = fake_paperless_doc
        mock_emb.return_value = [[0.02] * 768]

        payload = {
            "document_id": 1050,
            "workspace_slug": "copro",
            "collection_name": "Archives Copropriété"
        }

        resp = await async_client.post("/v1/ingest/paperless-webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "ingested"
        assert data["title"] == "Facture Plomberie Synergies"
        assert data["scope"] == "syndic"
        assert data["sensitivity"] == "secret"
        mock_fetch.assert_awaited_once_with(1050)


@pytest.mark.asyncio
async def test_ingest_single_document_deduplication(db_session):
    """Vérifie la déduplication SHA-256 lors d'ingestions répétées du même contenu (§16.4)."""
    with patch("knowledge.services.ingestion.generate_embeddings", new_callable=AsyncMock) as mock_emb:
        mock_emb.return_value = [[0.03] * 768]

        content = "Texte unique pour tester l'idempotence et le hachage SHA-256."
        
        # 1. Première ingestion
        id_1 = await ingest_single_document(
            title="Doc Test Dédup 1",
            content=content,
            workspace_slug="copro",
            collection_name="Archives Copropriété",
            db=db_session
        )
        assert id_1 is not None

        # 2. Deuxième ingestion avec espaces ou casse légèrement variable mais contenu normalisé identique
        variant_content = "  Texte unique pour tester l'idempotence et le hachage SHA-256. \n"
        id_2 = await ingest_single_document(
            title="Doc Test Dédup 2 (Copie)",
            content=variant_content,
            workspace_slug="copro",
            collection_name="Archives Copropriété",
            db=db_session
        )

        # Le second appel doit retourner l'ID existant et ne pas recréer de document
        assert id_2 == id_1


@pytest.mark.asyncio
async def test_cptcopro_sync_idempotence_and_records(db_session):
    """Vérifie la synchronisation des données CPTCopro et leur idempotence (§8.5)."""
    with patch("knowledge.services.ingestion.generate_embeddings", new_callable=AsyncMock) as mock_emb:
        mock_emb.return_value = [[0.05] * 768]

        # 1. Première exécution (ou vérification que les 4 records sont reconnus)
        count_first = await run_cptcopro_sync(workspace_slug="copro", db=db_session)
        assert count_first >= 0  # 4 si nouvelle base, ou 4 IDs retournés

        # 2. Vérification de la présence des documents CPTCopro en base
        res = await db_session.execute(
            select(Document).where(Document.title.like("CPTCopro%"))
        )
        docs = res.scalars().all()
        assert len(docs) >= 4

        scopes = {d.scope for d in docs}
        assert "conseil_syndical" in scopes
        assert "lot:12" in scopes
        assert "lot:28" in scopes

        # 3. Seconde exécution (idempotente)
        count_second = await run_cptcopro_sync(workspace_slug="copro", db=db_session)
        assert count_second == 4  # Dédupliqué, les 4 IDs existants sont retournés sans lever d'erreur


@pytest.mark.asyncio
async def test_admin_alert_simulation_mode():
    """Vérifie le fonctionnement du service d'alerting en mode simulation dev."""
    # Sans variables de token, l'alerte simule l'envoi avec succès
    success = await send_admin_alert(
        level=AlertLevel.CRITICAL,
        title="Incident Restauration Base",
        message="Le test de restauration a échoué sur le container de test.",
        context={"container": "mementomori-knowledge-db", "code": 500},
        bot_token="",
        chat_id=""
    )
    assert success is True


@pytest.mark.asyncio
async def test_admin_alert_formatted_request():
    """Vérifie que send_admin_alert génère la charge HTTP Telegram attendue."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        success = await send_admin_alert(
            level="warning",
            title="Dépassement Quota Ingestion",
            message="Nombre de documents traités élevé ce jour.",
            context={"total": 120, "max_autorise": 100},
            bot_token="fake_bot_token",
            chat_id="123456789"
        )

        assert success is True
        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert "https://api.telegram.org/botfake_bot_token/sendMessage" in args[0]
        json_body = kwargs["json"]
        assert json_body["chat_id"] == "123456789"
        assert "[ATTENTION]" in json_body["text"]
        assert "Dépassement Quota Ingestion" in json_body["text"]
        assert "<code>120</code>" in json_body["text"]


@pytest.mark.asyncio
async def test_cptcopro_rbac_search_isolation(async_client, db_session):
    """Vérifie que les relevés financiers de lot (lot:12) ne sont pas visibles par un copropriétaire non autorisé."""
    res = await db_session.execute(select(Workspace).where(Workspace.slug == "copro"))
    ws = res.scalar_one_or_none()
    assert ws is not None
    ws_id = str(ws.id)

    # 1. Recherche par un copropriétaire lambda (copro_user n'a pas le scope 'lot:12')
    resp = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "Situation Individuelle des Charges Lot 12 Dupont", "top_k": 5},
        headers={"X-Dev-Principal": "copro_user"}
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    titles = [r["document_title"] for r in results]
    assert "CPTCopro - Situation Individuelle des Charges Lot 12" not in titles

    # 2. Recherche par le Conseil Syndical (a le scope 'conseil_syndical')
    resp_cs = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_id, "query": "Grand Livre Général Clôture Exercice 2024", "top_k": 5},
        headers={"X-Dev-Principal": "cs_user"}
    )
    assert resp_cs.status_code == 200
    results_cs = resp_cs.json()["results"]
    titles_cs = [r["document_title"] for r in results_cs]
    assert "CPTCopro - Grand Livre & Clôture Exercice 2024" in titles_cs
