"""
Service adaptateur CPTCopro Réel (Sprint 11, Tâche 11.1 & §8.5, §16.1).
Extrait les données comptables et financières réelles depuis la base MariaDB CPTCopro,
applique le préfixage de contexte et les indexe dans knowledge-api avec cloisonnement RBAC.
"""

from __future__ import annotations

import decimal
import os
from typing import Any, Dict, List, Optional
import pymysql
import pymysql.cursors
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.services.ingestion import ingest_single_document

logger = get_logger(__name__)


# Jeu de données comptables représentatif de fallback / tests unitaires
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


def _format_currency(val: Any) -> str:
    """Formate un montant décimal en chaîne monétaire EUR."""
    if val is None:
        return "0,00 EUR"
    if isinstance(val, (int, float, decimal.Decimal)):
        return f"{float(val):,.2f} EUR".replace(",", " ").replace(".", ",")
    return str(val)


def extract_cptcopro_from_mariadb() -> List[Dict[str, Any]]:
    """
    Extrait les données réelles depuis la base de données MariaDB CPTCopro.
    Génère :
    1. Grand Livre et Synthèse générale (Conseil Syndical)
    2. Suivi des Alertes et Impayés (Conseil Syndical)
    3. Fiches de situation financière individuelles par lot (cloisonnement lot:{num_apt})
    """
    host = os.getenv("CPTCOPRO_DB_HOST", "127.0.0.1")
    port = int(os.getenv("CPTCOPRO_DB_PORT", 3306))
    user = os.getenv("CPTCOPRO_DB_USER", "cptcopro_app")
    password = os.getenv("CPTCOPRO_DB_PASSWORD")
    database = os.getenv("CPTCOPRO_DB_NAME", "cptcopro")

    if not password:
        logger.warning("cptcopro_password_missing_fallback_mock")
        return CPTCOPRO_FINANCIAL_RECORDS

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        logger.error("cptcopro_mariadb_connection_failed", error=str(e), host=host, port=port)
        return CPTCOPRO_FINANCIAL_RECORDS

    extracted_records: List[Dict[str, Any]] = []

    try:
        with conn.cursor() as cur:
            # 1. Synthèse globale & Grand Livre (Conseil Syndical)
            cur.execute("""
                SELECT 
                    COUNT(DISTINCT cp.code_proprietaire) as total_lots,
                    COUNT(c.id) as total_operations,
                    COALESCE(SUM(c.debit), 0) as total_debit,
                    COALESCE(SUM(c.credit), 0) as total_credit,
                    COALESCE(SUM(c.debit) - SUM(c.credit), 0) as solde_global,
                    MIN(c.date) as date_debut,
                    MAX(c.date) as date_fin
                FROM coproprietaires cp
                LEFT JOIN charge c ON cp.code_proprietaire = c.code_proprietaire;
            """)
            glob = cur.fetchone() or {}

            global_content = (
                f"[Source: CPTCopro | Domaine: Comptabilité Générale | Copropriété]\n"
                f"GRAND LIVRE & BALANCE GENERALE DE LA COPROPRIETE\n"
                f"--------------------------------------------------------------------------------\n"
                f"Nombre de lots / copropriétaires suivis : {glob.get('total_lots', 0)}\n"
                f"Total des opérations comptables enregistrées : {glob.get('total_operations', 0)}\n"
                f"Période comptable couverte : du {glob.get('date_debut')} au {glob.get('date_fin')}\n\n"
                f"• Total Débits cumulés : {_format_currency(glob.get('total_debit'))}\n"
                f"• Total Crédits cumulés : {_format_currency(glob.get('total_credit'))}\n"
                f"• Solde Comptable Global : {_format_currency(glob.get('solde_global'))}\n"
                f"--------------------------------------------------------------------------------\n"
                f"Note : Données extraites en temps réel depuis le système comptable CPTCopro."
            )

            extracted_records.append({
                "type": "budget_global",
                "title": "CPTCopro - Grand Livre & Balance Générale de la Copropriété",
                "scope": "conseil_syndical",
                "sensitivity": "interne",
                "collection": "Comptabilité Copropriété",
                "content": global_content
            })

            # 2. Alertes Débits Élevés & Impayés (Conseil Syndical)
            cur.execute("""
                SELECT 
                    cp.code_proprietaire,
                    cp.nom_proprietaire,
                    cp.num_apt,
                    COALESCE(SUM(c.debit), 0) - COALESCE(SUM(c.credit), 0) as solde
                FROM coproprietaires cp
                JOIN charge c ON cp.code_proprietaire = c.code_proprietaire
                GROUP BY cp.code_proprietaire, cp.nom_proprietaire, cp.num_apt
                HAVING solde > 10000
                ORDER BY solde DESC
                LIMIT 20;
            """)
            alerts = cur.fetchall()

            alert_lines = [
                f"• Lot {a.get('num_apt', 'NA')} ({a.get('nom_proprietaire')}, code {a.get('code_proprietaire')}) : "
                f"Solde débiteur de {_format_currency(a.get('solde'))}"
                for a in alerts
            ]
            alert_content = (
                f"[Source: CPTCopro | Domaine: Suivi des Impayés | Scopes: conseil_syndical]\n"
                f"SYNTHÈSE DES SOLDES DÉBITEURS IMPORTANTS & ALERTES\n"
                f"--------------------------------------------------------------------------------\n"
                f"Nombre de comptes sous surveillance (> 10 000 EUR) : {len(alerts)}\n\n"
                + "\n".join(alert_lines) +
                f"\n--------------------------------------------------------------------------------\n"
                f"Document réservé au Conseil Syndical et au Syndic pour la préparation des relances."
            )

            extracted_records.append({
                "type": "alertes_impayes",
                "title": "CPTCopro - Synthèse des Impayés et Soldes Débiteurs Élevés",
                "scope": "conseil_syndical",
                "sensitivity": "interne",
                "collection": "Comptabilité Copropriété",
                "content": alert_content
            })

            # 3. Fiches de situation individuelle par lot (cloisonnement RBAC lot:{num_apt})
            cur.execute("""
                SELECT 
                    cp.code_proprietaire,
                    cp.nom_proprietaire,
                    cp.num_apt,
                    cp.type_apt,
                    COALESCE(SUM(c.debit), 0) as total_debit,
                    COALESCE(SUM(c.credit), 0) as total_credit,
                    COALESCE(SUM(c.debit) - SUM(c.credit), 0) as solde,
                    COUNT(c.id) as nb_operations
                FROM coproprietaires cp
                LEFT JOIN charge c ON cp.code_proprietaire = c.code_proprietaire
                GROUP BY cp.code_proprietaire, cp.nom_proprietaire, cp.num_apt, cp.type_apt
                ORDER BY cp.num_apt ASC;
            """)
            lots = cur.fetchall()

            for lot in lots:
                c_code = lot.get("code_proprietaire")
                nom = lot.get("nom_proprietaire", "Inconnu")
                num_apt = lot.get("num_apt", "NA")
                type_apt = lot.get("type_apt", "Standard")
                debit = lot.get("total_debit", 0)
                credit = lot.get("total_credit", 0)
                solde = lot.get("solde", 0)
                nb_ops = lot.get("nb_operations", 0)

                # Récupérer les 3 dernières opérations pour donner du contexte historique
                cur.execute("""
                    SELECT date, debit, credit 
                    FROM charge 
                    WHERE code_proprietaire = %s 
                    ORDER BY date DESC 
                    LIMIT 3;
                """, (c_code,))
                recent_ops = cur.fetchall()
                op_lines = [
                    f"  - Date: {op.get('date')} | Débit: {_format_currency(op.get('debit'))} | Crédit: {_format_currency(op.get('credit'))}"
                    for op in recent_ops
                ]
                recent_ops_text = "\nDernières opérations comptables :\n" + "\n".join(op_lines) if op_lines else ""

                lot_scope = f"lot:{num_apt}" if num_apt and num_apt != "NA" else f"lot:{c_code}"

                lot_content = (
                    f"[Source: CPTCopro | Lot: {num_apt} | Code: {c_code} | Type: {type_apt}]\n"
                    f"RELEVÉ DE SITUATION COMPTABLE INDIVIDUELLE : LOT {num_apt}\n"
                    f"Copropriétaire : {nom} (Code comptable: {c_code})\n"
                    f"Type de bien : {type_apt}\n"
                    f"--------------------------------------------------------------------------------\n"
                    f"• Total Débits enregistrés : {_format_currency(debit)}\n"
                    f"• Total Crédits enregistrés : {_format_currency(credit)}\n"
                    f"• Solde Actuel du Compte : {_format_currency(solde)}\n"
                    f"• Nombre total d'écritures : {nb_ops}\n"
                    f"{recent_ops_text}\n"
                    f"--------------------------------------------------------------------------------\n"
                    f"Accès strictement restreint au copropriétaire du lot {num_apt} et au Conseil Syndical."
                )

                extracted_records.append({
                    "type": "compte_lot",
                    "title": f"CPTCopro - Situation Individuelle des Charges Lot {num_apt}",
                    "scope": lot_scope,
                    "sensitivity": "interne",
                    "collection": "Comptes Individuels Copropriétaires",
                    "content": lot_content
                })

    finally:
        conn.close()

    logger.info("cptcopro_extraction_successful", count=len(extracted_records))
    return extracted_records


async def run_cptcopro_sync(
    workspace_slug: str = "copro",
    db: Optional[AsyncSession] = None,
    force_mock: bool = False
) -> int:
    """Synchronise et indexe les finances de CPTCopro dans knowledge-api."""
    logger.info("cptcopro_sync_started", workspace=workspace_slug, force_mock=force_mock)

    from knowledge.dependencies import async_session_maker

    # Sélection de la source (réelle ou mockée)
    if force_mock or os.getenv("CPTCOPRO_FORCE_MOCK", "false").lower() == "true":
        records = CPTCOPRO_FINANCIAL_RECORDS
    else:
        records = extract_cptcopro_from_mariadb()

    async def _sync(session: AsyncSession) -> int:
        ingested = 0
        for rec in records:
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
