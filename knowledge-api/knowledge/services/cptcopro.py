"""
Service adaptateur CPTCopro (Sprint 6, Tâche 6.5 & §8.5, §16.1).
Extrait les données comptables et financières de la copropriété (budgets, comptes, lots),
applique le préfixage de contexte et les indexe dans knowledge-api avec cloisonnement RBAC.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from knowledge.logging import get_logger
from knowledge.models import Workspace, Collection, Source
from knowledge.services.ingestion import ingest_single_document

logger = get_logger(__name__)


# Jeu de données comptables représentatif de CPTCopro pour la résidence Les Jardins de Provence
CPTCOPRO_FINANCIAL_RECORDS = [
    {
        "type": "budget_global",
        "title": "CPTCopro - Grand Livre & Clôture Exercice 2024",
        "scope": "conseil_syndical",
        "sensitivity": "interne",
        "collection": "Comptabilité Copropriété",
        "content": (
            "COPROPRIETE LES JARDINS DE PROVENCE - LOGICIEL CPTCOPRO\n"
            "GRAND LIVRE GENERAL - EXERCICE CLOS AU 31/12/2024\n"
            "--------------------------------------------------------------------------------\n"
            "Total des charges réelles de fonctionnement 2024 : 46 210,00 EUR.\n"
            "- Compte 601 (Eau froide générale) : 4 120,00 EUR\n"
            "- Compte 602 (Électricité parties communes) : 2 850,00 EUR\n"
            "- Compte 605 (Chauffage collectif et maintenance chaudière) : 18 400,00 EUR\n"
            "- Compte 614 (Contrats de maintenance : ascenseur, extincteurs) : 5 180,00 EUR\n"
            "- Compte 615 (Entretien courant espaces verts et nettoyage) : 7 860,00 EUR\n"
            "- Compte 621 (Honoraires de syndic Cabinet Mer & Soleil) : 6 200,00 EUR\n"
            "- Compte 622 (Assurance multirisque immeuble AXA) : 1 600,00 EUR\n"
            "\n"
            "Solde bancaire de la copropriété au 31/12/2024 : 14 380,50 EUR (Banque Populaire).\n"
            "Fonds de réserve travaux (Loi ALUR) : 12 500,00 EUR sur livret A bloqué.\n"
        )
    },
    {
        "type": "budget_previsionnel",
        "title": "CPTCopro - Budget Prévisionnel Détaillé 2026",
        "scope": "conseil_syndical",
        "sensitivity": "interne",
        "collection": "Comptabilité Copropriété",
        "content": (
            "COPROPRIETE LES JARDINS DE PROVENCE - LOGICIEL CPTCOPRO\n"
            "BUDGET PREVISIONNEL APPROUVE POUR L'EXERCICE 2026 : 48 000,00 EUR\n"
            "--------------------------------------------------------------------------------\n"
            "Postes prévisionnels de dépenses 2026 :\n"
            "1. Chauffage collectif urbain : 19 000,00 EUR\n"
            "2. Entretien des espaces verts (Vert Avenir) : 5 000,00 EUR\n"
            "3. Maintenance ascenseur Bat A (Contrat OTIS) : 4 320,00 EUR TTC\n"
            "4. Eau et électricité communes : 7 200,00 EUR\n"
            "5. Honoraires de syndic : 6 480,00 EUR\n"
            "6. Assurance et frais bancaires : 2 000,00 EUR\n"
            "7. Menus travaux et imprévus : 4 000,00 EUR\n"
            "\n"
            "Échéancier des appels de fonds 2026 : 12 000,00 EUR au 1er janvier, 1er avril, 1er juillet, 1er octobre.\n"
        )
    },
    {
        "type": "compte_lot",
        "title": "CPTCopro - Situation Individuelle des Charges Lot 12",
        "scope": "lot:12",
        "sensitivity": "interne",
        "collection": "Comptes Individuels Copropriétaires",
        "content": (
            "COPROPRIETE LES JARDINS DE PROVENCE - CPTCOPRO EXTRACTION\n"
            "RELEVE DE COMPTE INDIVIDUEL : LOT 12 (M. Pierre Dupont)\n"
            "Quote-part générale : 38 / 1000èmes.\n"
            "--------------------------------------------------------------------------------\n"
            "- Appel de fonds T1 2026 (01/01/2026) : 456,00 EUR (Payé le 05/01/2026)\n"
            "- Appel de fonds T2 2026 (01/04/2026) : 456,00 EUR (En attente d'échéance)\n"
            "Solde comptable actuel du Lot 12 au 01/04/2026 : 0,00 EUR (Compte à jour).\n"
        )
    },
    {
        "type": "compte_lot",
        "title": "CPTCopro - Situation Individuelle des Charges Lot 28",
        "scope": "lot:28",
        "sensitivity": "interne",
        "collection": "Comptes Individuels Copropriétaires",
        "content": (
            "COPROPRIETE LES JARDINS DE PROVENCE - CPTCOPRO EXTRACTION\n"
            "RELEVE DE COMPTE INDIVIDUEL : LOT 28 (Mme Sophie Laurent)\n"
            "Quote-part générale : 42 / 1000èmes.\n"
            "--------------------------------------------------------------------------------\n"
            "- Appel de fonds T1 2026 (01/01/2026) : 504,00 EUR (Payé le 12/01/2026)\n"
            "- Régularisation charges 2025 : Crédit de 35,40 EUR\n"
            "Solde comptable actuel du Lot 28 au 01/04/2026 : -35,40 EUR (Créditeur).\n"
        )
    }
]


async def run_cptcopro_sync(
    workspace_slug: str = "copro-jardins",
    db: Optional[AsyncSession] = None
) -> int:
    """Synchronise et indexe les finances de CPTCopro dans knowledge-api."""
    logger.info("cptcopro_sync_started", workspace=workspace_slug)

    from knowledge.dependencies import async_session_maker

    async def _sync(session: AsyncSession) -> int:
        ingested = 0
        for rec in CPTCOPRO_FINANCIAL_RECORDS:
            doc_id = await ingest_single_document(
                title=rec["title"],
                content=rec["content"],
                workspace_slug=workspace_slug,
                collection_name=rec["collection"],
                db=session,
                source_type="cptcopro",
                scope=rec["scope"],
                sensitivity=rec["sensitivity"],
                original_ref=f"cptcopro://{rec['type']}/{rec['title']}",
                metadata_={"source_adapter": "cptcopro", "record_type": rec["type"]}
            )
            if doc_id:
                ingested += 1
        return ingested

    if db:
        count = await _sync(db)
    else:
        async with async_session_maker() as session:
            count = await _sync(session)

    logger.info("cptcopro_sync_completed", ingested_count=count)
    return count
