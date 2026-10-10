"""
Script d'initialisation et d'application des politiques RBAC (Sprint 5).
Configure les 3 rôles canoniques de copropriété (Copropriétaire, CS, Admin),
l'isolation inter-workspaces (copro vs sante-perso) et les fragments sensibles.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

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
)
from knowledge.services.embedding import generate_embedding

load_dotenv()

async def seed_rbac():
    print("=" * 60)
    print("MEMENTOMORI - Initialisation RBAC & Politiques de Sécurité")
    print("=" * 60)

    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        # 1. Workspace copro
        ws_copro = (await session.execute(
            select(Workspace).where(Workspace.slug == "copro")
        )).scalar_one_or_none()

        if not ws_copro:
            ws_copro = Workspace(
                name="Les Jardins de Provence",
                slug="copro",
                domain="pro",
                settings={"type": "copropriete", "address": "12 Rue des Fleurs, 13000 Marseille"}
            )
            session.add(ws_copro)
            await session.flush()
            print(f"  [+] Workspace créé : copro ({ws_copro.id})")
        else:
            print(f"  [=] Workspace existant : copro ({ws_copro.id})")

        # 2. Workspace sante-perso (pour vérification de non-fuite inter-workspaces)
        ws_sante = (await session.execute(
            select(Workspace).where(Workspace.slug == "sante-perso")
        )).scalar_one_or_none()

        if not ws_sante:
            ws_sante = Workspace(
                name="Santé Personnelle",
                slug="sante-perso",
                domain="perso",
                settings={"type": "sante"}
            )
            session.add(ws_sante)
            await session.flush()
            print(f"  [+] Workspace créé : sante-perso ({ws_sante.id})")
        else:
            print(f"  [=] Workspace existant : sante-perso ({ws_sante.id})")

        # Collections
        col_copro = (await session.execute(
            select(Collection).where(Collection.name == "Copropriété - Général")
        )).scalar_one_or_none()

        if not col_copro:
            col_copro = Collection(name="Copropriété - Général", classification="partage")
            session.add(col_copro)
            await session.flush()
            session.add(CollectionWorkspace(collection_id=col_copro.id, workspace_id=ws_copro.id))
            print(f"  [+] Collection créée : Copropriété - Général")

        col_sante = (await session.execute(
            select(Collection).where(Collection.name == "Dossier Médical")
        )).scalar_one_or_none()

        if not col_sante:
            col_sante = Collection(name="Dossier Médical", classification="confidentiel")
            session.add(col_sante)
            await session.flush()
            session.add(CollectionWorkspace(collection_id=col_sante.id, workspace_id=ws_sante.id))
            print(f"  [+] Collection créée : Dossier Médical (sante-perso)")

        # 3. Principals
        principals_data = [
            ("copro_user", "user", "Jean Dupont (Copropriétaire)"),
            ("copro_user_lot42", "user", "Alexandre Garcia (Lot 42)"),
            ("cs_user", "user", "Sophie Martin (Conseil Syndical)"),
            ("admin_user", "user", "Cabinet Mer & Soleil (Syndic Admin)"),
            ("csbot", "app", "CSBOT Telegram Assistant"),
            ("sante_user", "user", "Agent Santé Privé"),
        ]

        principals_map = {}
        for ext_id, p_type, name in principals_data:
            p = (await session.execute(
                select(Principal).where(Principal.external_id == ext_id)
            )).scalar_one_or_none()
            if not p:
                p = Principal(external_id=ext_id, type=p_type, display_name=name)
                session.add(p)
                await session.flush()
                print(f"  [+] Principal créé : {ext_id} ({p.id})")
            else:
                p.display_name = name
                print(f"  [=] Principal existant : {ext_id} ({p.id})")
            principals_map[ext_id] = p

        # 4. Politiques de sécurité (RBAC §4.2 & §5.3)
        policies_data = [
            # copro
            (
                ws_copro.id,
                principals_map["copro_user"].id,
                "coproprietaire",
                ["public", "copro", "collectif"],
                "interne",
                ["read", "search"]
            ),
            (
                ws_copro.id,
                principals_map["copro_user_lot42"].id,
                "coproprietaire",
                ["public", "copro", "collectif", "lot:42"],
                "interne",
                ["read", "search"]
            ),
            (
                ws_copro.id,
                principals_map["cs_user"].id,
                "cs",
                ["public", "copro", "collectif", "conseil_syndical"],
                "confidentiel",
                ["read", "search", "ingest"]
            ),
            (
                ws_copro.id,
                principals_map["admin_user"].id,
                "admin",
                ["public", "copro", "collectif", "conseil_syndical", "syndic", "lot:42", "owner"],
                "secret",
                ["read", "write", "search", "admin"]
            ),
            (
                ws_copro.id,
                principals_map["csbot"].id,
                "cs",
                ["public", "copro", "collectif", "conseil_syndical"],
                "interne",
                ["read", "search"]
            ),
            # sante-perso
            (
                ws_sante.id,
                principals_map["sante_user"].id,
                "owner",
                ["owner", "public"],
                "secret",
                ["read", "write", "search", "admin"]
            )
        ]

        for ws_id, princ_id, role, scopes, sens, actions in policies_data:
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
                print(f"  [+] Policy créée : role={role}, scopes={scopes}, max_sens={sens}")
            else:
                pol.role = role
                pol.allowed_scopes = scopes
                pol.max_sensitivity = sens
                pol.actions = actions
                print(f"  [*] Policy mise à jour : role={role}, scopes={scopes}, max_sens={sens}")

        await session.flush()

        # 5. Documents supplémentaires de test (Secret, Lot 42, Santé)
        # 5a. Document secret dans copro (Test 5.3)
        doc_secret = (await session.execute(
            select(Document).where(Document.title == "Codes d'accès et alarmes sécurisées")
        )).scalars().first()

        if not doc_secret:
            doc_secret = Document(
                collection_id=col_copro.id,
                title="Codes d'accès et alarmes sécurisées",
                status="actif",
                scope="syndic",
                sensitivity="secret",
                is_active=True,
                version=1
            )
            session.add(doc_secret)
            await session.flush()

            dv = DocumentVersion(
                document_id=doc_secret.id,
                version_number=1,
                extracted_text="Code alarme sous-sol : 9876. Cle armoire electrique : clef ronde n°4. Combinaison coffre syndic : 45-89-12."
            )
            session.add(dv)
            await session.flush()

            content = dv.extracted_text
            emb = await generate_embedding(content)
            frag = Fragment(
                document_version_id=dv.id,
                chunk_index=0,
                page_number=1,
                content=content,
                embedding=emb,
                context_prefix="copro > Syndic",
                citation_ref={"document_title": doc_secret.title, "page": 1}
            )
            session.add(frag)
            print(f"  [+] Document secret créé : '{doc_secret.title}' (scope=syndic, sens=secret)")

        # 5b. Document lot 42 dans copro (Test 5.6)
        doc_lot42 = (await session.execute(
            select(Document).where(Document.title == "Décompte individuel de charges 2025 - Lot 42")
        )).scalars().first()

        if not doc_lot42:
            doc_lot42 = Document(
                collection_id=col_copro.id,
                title="Décompte individuel de charges 2025 - Lot 42",
                status="actif",
                scope="lot:42",
                sensitivity="interne",
                is_active=True,
                version=1
            )
            session.add(doc_lot42)
            await session.flush()

            dv = DocumentVersion(
                document_id=doc_lot42.id,
                version_number=1,
                extracted_text="Decompte individuel de charges de copropriete 2025 pour le Lot 42 (M. Alexandre Garcia) : Solde debiteur 145.20 EUR a regler avant le 31/03/2026."
            )
            session.add(dv)
            await session.flush()

            content = dv.extracted_text
            emb = await generate_embedding(content)
            frag = Fragment(
                document_version_id=dv.id,
                chunk_index=0,
                page_number=1,
                content=content,
                embedding=emb,
                context_prefix="copro > Lot 42",
                citation_ref={"document_title": doc_lot42.title, "page": 1}
            )
            session.add(frag)
            print(f"  [+] Document lot:42 créé : '{doc_lot42.title}' (scope=lot:42, sens=interne)")

        # 5c. Document de santé dans sante-perso (Test 5.6 isolation inter-workspaces)
        doc_sante = (await session.execute(
            select(Document).where(Document.title == "Bilan Sanguin Annuel 2026")
        )).scalars().first()

        if not doc_sante:
            doc_sante = Document(
                collection_id=col_sante.id,
                title="Bilan Sanguin Annuel 2026",
                status="actif",
                scope="owner",
                sensitivity="confidentiel",
                is_active=True,
                version=1
            )
            session.add(doc_sante)
            await session.flush()

            dv = DocumentVersion(
                document_id=doc_sante.id,
                version_number=1,
                extracted_text="Analyses medicales Laboratoire Pasteur. Patient Alexandre. Glycemie a jeun : 0.94 g/L. Cholesterolemie totale : 1.85 g/L. Triglycerides normaux."
            )
            session.add(dv)
            await session.flush()

            content = dv.extracted_text
            emb = await generate_embedding(content)
            frag = Fragment(
                document_version_id=dv.id,
                chunk_index=0,
                page_number=1,
                content=content,
                embedding=emb,
                context_prefix="sante-perso > Analyses",
                citation_ref={"document_title": doc_sante.title, "page": 1}
            )
            session.add(frag)
            print(f"  [+] Document santé créé : '{doc_sante.title}' dans sante-perso")

        # 5d. Contrat ascenseur OTIS dans copro (Test 5.1 / 5.5)
        doc_otis = (await session.execute(
            select(Document).where(Document.title == "Contrat de maintenance ascenseur OTIS 2026")
        )).scalars().first()

        if not doc_otis:
            doc_otis = Document(
                collection_id=col_copro.id,
                title="Contrat de maintenance ascenseur OTIS 2026",
                status="actif",
                scope="conseil_syndical",
                sensitivity="confidentiel",
                is_active=True,
                version=1
            )
            session.add(doc_otis)
            await session.flush()

            dv_otis = DocumentVersion(
                document_id=doc_otis.id,
                version_number=1,
                extracted_text="Contrat de maintenance et entretien complet des ascenseurs OTIS 2026 pour la Residence Les Jardins. Prestataire: OTIS France. Ref: OTIS-MARS-2026-78492. Visite mensuelle obligatoire."
            )
            session.add(dv_otis)
            await session.flush()

            content_otis = dv_otis.extracted_text
            emb_otis = await generate_embedding(content_otis)
            frag_otis = Fragment(
                document_version_id=dv_otis.id,
                chunk_index=0,
                page_number=1,
                content=content_otis,
                embedding=emb_otis,
                context_prefix="copro > Conseil Syndical",
                citation_ref={"document_title": doc_otis.title, "page": 1}
            )
            session.add(frag_otis)
            print(f"  [+] Document OTIS créé : '{doc_otis.title}' (scope=conseil_syndical, sens=confidentiel)")

        await session.commit()

    await engine.dispose()
    print("=" * 60)
    print("Initialisation RBAC et documents de sécurité achevée avec succès !")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(seed_rbac())
