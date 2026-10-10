"""
Tests automatisés du Sprint 12 : Déploiement et Remplissage des 8 Workspaces & Collections Partagées.
Vérifie les exigences §3.1 (9 workspaces) et §3.2 (collections transversales many-to-many).
"""

import pytest
from sqlalchemy import select
from knowledge.models import Workspace, Collection, CollectionWorkspace, Document

@pytest.mark.asyncio
async def test_all_9_workspaces_exist_and_configured(db_session):
    """Vérifie l'existence et la conformité des 9 workspaces de la vision (§3.1)."""
    expected_workspaces = {
        "copro": "pro",
        "finances-perso": "perso",
        "admin-perso": "perso",
        "sante-perso": "perso",
        "entreprise": "pro",
        "dev": "pro",
        "formation": "perso",
        "consulting": "pro",
        "veille": "pro",
    }

    res = await db_session.execute(select(Workspace))
    workspaces = {w.slug: w for w in res.scalars().all()}

    for slug, domain in expected_workspaces.items():
        assert slug in workspaces, f"Workspace '{slug}' manquant en base !"
        assert workspaces[slug].domain == domain, f"Domaine incorrect pour '{slug}' : attendu {domain}, obtenu {workspaces[slug].domain}"


@pytest.mark.asyncio
async def test_shared_collections_many_to_many_linking(db_session):
    """Vérifie que les 3 collections partagées transversales sont bien liées en Many-to-Many (§3.2)."""
    expected_shared = {
        "juridique-general": ["copro", "admin-perso", "entreprise"],
        "fiscal": ["finances-perso", "entreprise"],
        "templates": ["dev", "consulting", "entreprise"],
    }

    res_ws = await db_session.execute(select(Workspace))
    ws_map = {w.slug: w.id for w in res_ws.scalars().all()}

    for col_name, target_slugs in expected_shared.items():
        res_col = await db_session.execute(select(Collection).where(Collection.name == col_name))
        col = res_col.scalar_one_or_none()
        assert col is not None, f"Collection partagée '{col_name}' introuvable !"
        assert col.classification == "partage"

        res_links = await db_session.execute(
            select(CollectionWorkspace.workspace_id).where(CollectionWorkspace.collection_id == col.id)
        )
        linked_ws_ids = set(res_links.scalars().all())

        for slug in target_slugs:
            expected_id = ws_map.get(slug)
            assert expected_id in linked_ws_ids, f"Liaison manquante : '{col_name}' <-> '{slug}'"


@pytest.mark.asyncio
async def test_shared_collection_search_cross_workspace(async_client, db_session):
    """Vérifie qu'un document partagé transversalement est interrogeable depuis tous ses workspaces liés."""
    res_ws = await db_session.execute(select(Workspace))
    ws_map = {w.slug: str(w.id) for w in res_ws.scalars().all()}

    # 1. 'juridique-general' (Code Civil) accessible depuis copro, admin-perso, entreprise
    for slug in ["copro", "admin-perso", "entreprise"]:
        ws_id = ws_map[slug]
        resp = await async_client.post(
            "/v1/search",
            json={"workspace_id": ws_id, "query": "Code Civil Article 544 propriete contrat", "top_k": 5},
            headers={"X-Dev-Principal": "admin_user"}
        )
        assert resp.status_code == 200, f"Erreur de recherche sur {slug} : {resp.text}"
        data = resp.json()
        titles = [r["document_title"] for r in data["results"]]
        assert any("Code Civil" in t for t in titles), f"Document 'Code Civil' introuvable depuis le workspace '{slug}' !"

    # 2. 'fiscal' accessible depuis finances-perso et entreprise
    for slug in ["finances-perso", "entreprise"]:
        ws_id = ws_map[slug]
        resp = await async_client.post(
            "/v1/search",
            json={"workspace_id": ws_id, "query": "Bareme Impot sur le Revenu tranches fiscales", "top_k": 5},
            headers={"X-Dev-Principal": "admin_user"}
        )
        assert resp.status_code == 200, f"Erreur de recherche sur {slug} : {resp.text}"
        data = resp.json()
        titles = [r["document_title"] for r in data["results"]]
        assert any("Barème de l'Impôt" in t for t in titles), f"Document fiscal introuvable depuis le workspace '{slug}' !"

    # 3. 'templates' accessible depuis dev, consulting et entreprise
    for slug in ["dev", "consulting", "entreprise"]:
        ws_id = ws_map[slug]
        resp = await async_client.post(
            "/v1/search",
            json={"workspace_id": ws_id, "query": "Contrat de Prestation de Services Intellectuels", "top_k": 5},
            headers={"X-Dev-Principal": "admin_user"}
        )
        assert resp.status_code == 200, f"Erreur de recherche sur {slug} : {resp.text}"
        data = resp.json()
        titles = [r["document_title"] for r in data["results"]]
        assert any("Modèle Universel de Contrat" in t for t in titles), f"Document templates introuvable depuis le workspace '{slug}' !"


@pytest.mark.asyncio
async def test_strict_inter_workspace_isolation(async_client, db_session):
    """Vérifie l'étanchéité stricte inter-workspaces (zéro fuite de données entre silos)."""
    res_ws = await db_session.execute(select(Workspace))
    ws_map = {w.slug: str(w.id) for w in res_ws.scalars().all()}

    # Document finances-perso (Relevé bancaire BNP) interrogé depuis copro -> DOIT ÊTRE INTROUVABLE
    resp_copro = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_map["copro"], "query": "Releve Bancaire Compte Courant BNP Paribas", "top_k": 5},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_copro.status_code == 200
    titles_copro = [r["document_title"] for r in resp_copro.json()["results"]]
    assert not any("Relevé Bancaire Compte Courant BNP" in t for t in titles_copro), "Fuite de relevé bancaire personnel dans le workspace copro !"

    # Document sante-perso (Ordonnance médicale) interrogé depuis entreprise -> DOIT ÊTRE INTROUVABLE
    resp_ent = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_map["entreprise"], "query": "Ordonnance Medicale Traitement Allergique", "top_k": 5},
        headers={"X-Dev-Principal": "admin_user"}
    )
    assert resp_ent.status_code == 200
    titles_ent = [r["document_title"] for r in resp_ent.json()["results"]]
    assert not any("Ordonnance Médicale" in t for t in titles_ent), "Fuite de données médicales dans le workspace entreprise !"

    # Document dev interrogé depuis sante-perso -> DOIT ÊTRE INTROUVABLE
    resp_sante = await async_client.post(
        "/v1/search",
        json={"workspace_id": ws_map["sante-perso"], "query": "Architecture & Spécification du Moteur RAG", "top_k": 5},
        headers={"X-Dev-Principal": "sante_user"}
    )
    assert resp_sante.status_code == 200
    titles_sante = [r["document_title"] for r in resp_sante.json()["results"]]
    assert not any("Architecture & Spécification" in t for t in titles_sante), "Fuite de doc dev dans le workspace santé !"
