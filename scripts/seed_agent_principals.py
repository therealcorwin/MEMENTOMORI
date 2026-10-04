"""
Script d'initialisation des Service Accounts Agents & Workspaces Multi-projets (Sprint 7, Tâches 7.1, 7.2, 7.6, 7.7).
Crée les workspaces 'finances-perso' et 'dev', les collections dédiées et partagées (many-to-many),
les principals des sous-agents et de l'orchestrateur, ainsi que les documents représentatifs.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# Ajout du path knowledge-api
sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-api"))

from knowledge.config import settings
from knowledge.models import (
    Workspace,
    Collection,
    CollectionWorkspace,
    Document,
    DocumentVersion,
    Fragment,
    Principal,
    Policy,
    Source
)
from knowledge.services.embedding import generate_embeddings
from knowledge.services.chunking import split_into_chunks
from knowledge.services.dedup import compute_content_hash


async def seed_agents_and_workspaces():
    print("=" * 70)
    print("MEMENTOMORI - Initialisation Multi-Agents & Workspaces (Sprint 7)")
    print("=" * 70)

    engine = create_async_engine(settings.DATABASE_URL)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        # 1. Récupération des workspaces existants
        ws_copro = (await session.execute(
            select(Workspace).where(Workspace.slug == "copro-jardins")
        )).scalar_one_or_none()
        ws_sante = (await session.execute(
            select(Workspace).where(Workspace.slug == "sante-perso")
        )).scalar_one_or_none()

        assert ws_copro is not None, "Workspace copro-jardins introuvable. Exécuter d'abord seed_rbac_policies.py"

        # 2. Création du workspace finances-perso (Tâche 7.6)
        ws_finances = (await session.execute(
            select(Workspace).where(Workspace.slug == "finances-perso")
        )).scalar_one_or_none()

        if not ws_finances:
            ws_finances = Workspace(
                name="Finances & Patrimoine Personnel",
                slug="finances-perso",
                domain="perso",
                settings={
                    "type": "finances",
                    "description": "Comptes bancaires personnels, impôts, budget, épargne, investissements"
                }
            )
            session.add(ws_finances)
            await session.flush()
            print(f"[+] Workspace créé : finances-perso ({ws_finances.id})")
        else:
            print(f"[=] Workspace existant : finances-perso ({ws_finances.id})")

        # 3. Création du workspace dev
        ws_dev = (await session.execute(
            select(Workspace).where(Workspace.slug == "dev")
        )).scalar_one_or_none()

        if not ws_dev:
            ws_dev = Workspace(
                name="Développement & Infrastructure",
                slug="dev",
                domain="pro",
                settings={
                    "type": "dev",
                    "description": "Code source, documentation technique, scripts, architecture Docker, Git"
                }
            )
            session.add(ws_dev)
            await session.flush()
            print(f"[+] Workspace créé : dev ({ws_dev.id})")
        else:
            print(f"[=] Workspace existant : dev ({ws_dev.id})")

        # 4. Collections dédiées
        col_finances = (await session.execute(
            select(Collection).where(Collection.name == "Comptes & Banque")
        )).scalar_one_or_none()
        if not col_finances:
            col_finances = Collection(name="Comptes & Banque", classification="confidentiel")
            session.add(col_finances)
            await session.flush()
            session.add(CollectionWorkspace(collection_id=col_finances.id, workspace_id=ws_finances.id))
            print(f"[+] Collection créée : Comptes & Banque (finances-perso)")

        col_dev = (await session.execute(
            select(Collection).where(Collection.name == "Documentation Technique")
        )).scalar_one_or_none()
        if not col_dev:
            col_dev = Collection(name="Documentation Technique", classification="equipe")
            session.add(col_dev)
            await session.flush()
            session.add(CollectionWorkspace(collection_id=col_dev.id, workspace_id=ws_dev.id))
            print(f"[+] Collection créée : Documentation Technique (dev)")

        # 5. Collection partagée many-to-many (Tâche 7.7)
        # Liée à la fois à copro-jardins ET à finances-perso
        col_shared = (await session.execute(
            select(Collection).where(Collection.name == "Justificatifs & Paiements Transverses")
        )).scalar_one_or_none()
        if not col_shared:
            col_shared = Collection(name="Justificatifs & Paiements Transverses", classification="partage")
            session.add(col_shared)
            await session.flush()
            session.add(CollectionWorkspace(collection_id=col_shared.id, workspace_id=ws_copro.id))
            session.add(CollectionWorkspace(collection_id=col_shared.id, workspace_id=ws_finances.id))
            print(f"[+] Collection partagée (many-to-many) créée : {col_shared.name} (copro + finances)")
        else:
            print(f"[=] Collection partagée existante : {col_shared.name}")

        # 6. Service Accounts Principals (§8.4, Tâche 7.1)
        agents_data = [
            ("agent-finances", "app", "Agent IA Finances"),
            ("agent-sante", "app", "Agent IA Santé"),
            ("agent-dev", "app", "Agent IA Développement"),
            ("orchestrator", "app", "Orchestrateur Central Multi-Agents"),
        ]

        principals_map = {}
        for ext_id, p_type, name in agents_data:
            p = (await session.execute(
                select(Principal).where(Principal.external_id == ext_id)
            )).scalar_one_or_none()
            if not p:
                p = Principal(external_id=ext_id, type=p_type, display_name=name)
                session.add(p)
                await session.flush()
                print(f"[+] Service Account créé : {ext_id} ({p.id})")
            else:
                p.display_name = name
                print(f"[=] Service Account existant : {ext_id} ({p.id})")
            principals_map[ext_id] = p

        # 7. Policies en base (§8.4, Tâche 7.2)
        # Note : L'orchestrateur n'a AUCUNE policy (Tâche 7.5 : Pas d'accès direct aux données)
        agent_policies = [
            (
                ws_finances.id,
                principals_map["agent-finances"].id,
                "reader",
                ["finances", "owner", "public"],
                "confidentiel",
                ["read", "search"]
            ),
            (
                ws_sante.id,
                principals_map["agent-sante"].id,
                "reader",
                ["sante", "owner", "public"],
                "confidentiel",
                ["read", "search"]
            ),
            (
                ws_dev.id,
                principals_map["agent-dev"].id,
                "reader",
                ["dev", "public"],
                "interne",
                ["read", "search"]
            ),
        ]

        for ws_id, princ_id, role, scopes, sens, actions in agent_policies:
            pol = (await session.execute(
                select(Policy).where(
                    Policy.workspace_id == ws_id,
                    Policy.principal_id == princ_id
                )
            )).scalar_one_or_none()

            if not pol:
                pol = Policy(
                    workspace_id=ws_id,
                    principal_id=princ_id,
                    role=role,
                    allowed_scopes=scopes,
                    max_sensitivity=sens,
                    actions=actions
                )
                session.add(pol)
                print(f"[+] Policy créée pour principal {princ_id} sur workspace {ws_id} (sens: {sens})")
            else:
                pol.allowed_scopes = scopes
                pol.max_sensitivity = sens
                pol.actions = actions
                print(f"[=] Policy mise à jour pour principal {princ_id} sur workspace {ws_id}")

        await session.commit()

        # 8. Insertion des documents pilotes pour les nouveaux workspaces
        print("\n[+] Indexation des documents de test multi-workspaces...")

        # Pré-extraction des identifiants primitifs
        ws_finances_id = ws_finances.id
        ws_finances_slug = ws_finances.slug
        col_finances_id = col_finances.id

        ws_dev_id = ws_dev.id
        ws_dev_slug = ws_dev.slug
        col_dev_id = col_dev.id

        col_shared_id = col_shared.id

        # Helper d'ingestion synchrone de documents
        async def insert_doc(
            ws_id,
            ws_slug: str,
            col_id,
            title: str,
            content: str,
            scope: str,
            sensitivity: str
        ):
            c_hash = compute_content_hash(content)
            existing = (await session.execute(
                select(Document).where(
                    Document.collection_id == col_id,
                    Document.title == title
                )
            )).scalar_one_or_none()

            if existing:
                print(f"  [=] Document déjà présent : '{title}'")
                return existing.id

            src = (await session.execute(
                select(Source).where(Source.workspace_id == ws_id, Source.connector_type == "manual_seed")
            )).scalar_one_or_none()
            if not src:
                src = Source(workspace_id=ws_id, connector_type="manual_seed", auto_approve=True)
                session.add(src)
                await session.flush()

            doc = Document(
                collection_id=col_id,
                source_id=src.id,
                title=title,
                status="actif",
                scope=scope,
                sensitivity=sensitivity,
                content_hash=c_hash,
                is_active=True,
                version=1
            )
            session.add(doc)
            await session.flush()

            doc_ver = DocumentVersion(
                document_id=doc.id,
                version_number=1,
                extracted_text=content
            )
            session.add(doc_ver)
            await session.flush()

            chunks = split_into_chunks(content, title, ws_slug)
            texts_to_embed = [f"{c.context_prefix}\n{c.content}" for c in chunks]
            embeddings = await generate_embeddings(texts_to_embed)

            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                frag = Fragment(
                    document_version_id=doc_ver.id,
                    chunk_index=idx,
                    content=chunk.content,
                    context_prefix=chunk.context_prefix,
                    page_number=1,
                    embedding=emb
                )
                session.add(frag)

            await session.commit()
            print(f"  [+] Document indexé avec succès : '{title}' ({len(chunks)} chunks)")
            return doc.id

        # Documents finances-perso
        await insert_doc(
            ws_id=ws_finances_id,
            ws_slug=ws_finances_slug,
            col_id=col_finances_id,
            title="Relevé de Compte Courant & Épargne - Janvier 2026",
            content=(
                "BANQUE POPULAIRE MEDITERRANEE - COMPTE COURANT PERSONNEL\n"
                "Titulaire du compte : M. Pierre Dupont\n"
                "Relevé au 31 janvier 2026.\n"
                "--------------------------------------------------------------------------------\n"
                "- Solde créditeur compte de dépôt : 4 250,00 EUR.\n"
                "- Livret A (Épargne de précaution disponible) : 15 000,00 EUR (taux 3,00%).\n"
                "- Solde total de liquidités immédiatement mobilisables : 19 250,00 EUR.\n"
                "Moyenne des charges et dépenses courantes mensuelles : 1 800,00 EUR/mois.\n"
                "Capacité résiduelle nette d'épargne mensuelle : 650,00 EUR."
            ),
            scope="finances",
            sensitivity="confidentiel"
        )

        await insert_doc(
            ws_id=ws_finances_id,
            ws_slug=ws_finances_slug,
            col_id=col_finances_id,
            title="Avis d'Imposition 2025 sur les Revenus 2024",
            content=(
                "REPUBLIQUE FRANCAISE - DIRECTION GENERALE DES FINANCES PUBLIQUES\n"
                "AVIS D'IMPOT 2025 SUR LES REVENUS DE L'ANNEE 2024\n"
                "Déclarant : Pierre Dupont\n"
                "--------------------------------------------------------------------------------\n"
                "Revenu brut global : 52 000 EUR\n"
                "Revenu fiscal de référence (RFR) : 48 500 EUR\n"
                "Nombre de parts : 1 part.\n"
                "Montant total net de l'impôt sur le revenu 2024 : 2 400,00 EUR.\n"
                "Mode de règlement : Prélèvement mensuel automatique (240,00 EUR / mois).\n"
                "Échéance finale du solde régularisée au 15 septembre 2025 (compte à jour)."
            ),
            scope="finances",
            sensitivity="confidentiel"
        )

        # Document dev
        await insert_doc(
            ws_id=ws_dev_id,
            ws_slug=ws_dev_slug,
            col_id=col_dev_id,
            title="Guide Déploiement Docker & Stack MEMENTOMORI",
            content=(
                "GUIDE TECHNIQUE MEMENTOMORI - INFRASTRUCTURE ET DEPLOIEMENT\n"
                "--------------------------------------------------------------------------------\n"
                "Pour déployer ou mettre à jour la stack de services Docker, exécuter docker-compose.knowledge.yml.\n"
                "Règle de persistance P7 : Tous les volumes de conteneurs sont montés sous D:\\Dev\\Docker\\MEMENTOMORI.\n"
                "Services de l'infrastructure :\n"
                "- PostgreSQL 16 + pgvector : port conteneur 5432 (port hôte 5433)\n"
                "- Redis 7 : port conteneur 6379 (port hôte 6380)\n"
                "- Traefik v3.3 : reverse proxy sécurisé ports 80 et 443 avec certificats Let's Encrypt\n"
                "- Authentik : port 9000 (IdP OAuth2 et gestionnaire d'identités)\n"
                "- Paperless-ngx : port 8000 (OCR et gestion documentaire)"
            ),
            scope="dev",
            sensitivity="interne"
        )

        # Document dans la collection partagée (Copro + Finances)
        await insert_doc(
            ws_id=ws_finances_id,  # Déposé dans la collection transversale
            ws_slug=ws_finances_slug,
            col_id=col_shared_id,
            title="Prélèvement Bancaire Automatique - Appel de Fonds Copropriété T1 2026",
            content=(
                "AVIS D'OPERATION BANCAIRE & JUSTIFICATIF DE PAIEMENT - BANQUE POPULAIRE\n"
                "--------------------------------------------------------------------------------\n"
                "Débit sur compte courant : -456,00 EUR au profit de Syndic Cabinet Mer & Soleil.\n"
                "Motif de l'opération : Règlement appel de fonds copropriété Les Jardins de Provence T1 2026.\n"
                "Lot concerné : Lot 12 (Appartement Bat A).\n"
                "Date d'exécution comptable : 05/01/2026.\n"
                "Solde du compte courant après débit : 4 250,00 EUR."
            ),
            scope="public",
            sensitivity="interne"
        )

    print("\n" + "=" * 70)
    print("Initialisation Multi-Agents & Workspaces Terminée avec Succès !")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_agents_and_workspaces())
