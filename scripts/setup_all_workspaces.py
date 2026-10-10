"""
Script de déploiement et de peuplement des 8 Workspaces & Collections transversales (Sprint 12).
Conforme à l'architecture cible (§3.1, §3.2) et aux règles de sécurité AGENTS.md.
Idempotent : ne supprime jamais de workspace existant, déduplication SHA-256.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

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
from knowledge.services.embedding import generate_embedding
from knowledge.services.chunking import split_into_chunks
from knowledge.services.dedup import compute_content_hash, check_duplicate

load_dotenv()

# Définition des 8 workspaces cibles
WORKSPACES_SPEC = [
    {
        "slug": "finances-perso",
        "name": "Finances Personnelles",
        "domain": "perso",
        "settings": {"type": "finances", "currency": "EUR"},
        "collections": [
            {"name": "Comptes & Relevés Bancaires", "classification": "confidentiel"},
            {"name": "Fiscalité Personnelle (Avis IRPP & Taxes)", "classification": "confidentiel"},
        ]
    },
    {
        "slug": "admin-perso",
        "name": "Administration Personnelle",
        "domain": "perso",
        "settings": {"type": "administratif"},
        "collections": [
            {"name": "Identité & État Civil", "classification": "confidentiel"},
            {"name": "Assurances & Logement", "classification": "confidentiel"},
        ]
    },
    {
        "slug": "sante-perso",
        "name": "Santé Personnelle",
        "domain": "perso",
        "settings": {"type": "sante"},
        "collections": [
            {"name": "Dossier Médical", "classification": "confidentiel"},
            {"name": "Analyses & Prescriptions", "classification": "confidentiel"},
        ]
    },
    {
        "slug": "entreprise",
        "name": "Entreprise & Activité Professionnelle",
        "domain": "pro",
        "settings": {"type": "societe", "statut": "independant"},
        "collections": [
            {"name": "Facturation & Devis", "classification": "confidentiel"},
            {"name": "Déclarations & Cotisations URSSAF", "classification": "confidentiel"},
        ]
    },
    {
        "slug": "dev",
        "name": "Développement & Ingénierie Logicielle",
        "domain": "pro",
        "settings": {"type": "technique"},
        "collections": [
            {"name": "Documentation Technique & Architecture", "classification": "equipe"},
            {"name": "Spécifications & Repositories", "classification": "equipe"},
        ]
    },
    {
        "slug": "formation",
        "name": "Formation & Fiches de Connaissance",
        "domain": "perso",
        "settings": {"type": "pedagogique"},
        "collections": [
            {"name": "Cours & Certifications", "classification": "prive"},
            {"name": "Fiches de Lecture & Synthèses", "classification": "prive"},
        ]
    },
    {
        "slug": "consulting",
        "name": "Consulting & Missions Clients",
        "domain": "pro",
        "settings": {"type": "prestation"},
        "collections": [
            {"name": "Missions & Livrables Clients", "classification": "equipe"},
            {"name": "Propositions Commerciales", "classification": "equipe"},
        ]
    },
    {
        "slug": "veille",
        "name": "Veille Technologique & Réglementaire",
        "domain": "pro",
        "settings": {"type": "veille"},
        "collections": [
            {"name": "Veille Technologique & IA", "classification": "equipe"},
            {"name": "Veille Réglementaire & Normes", "classification": "equipe"},
        ]
    },
]

# Collections transversales partagées (§3.2)
SHARED_COLLECTIONS_SPEC = [
    {
        "name": "juridique-general",
        "classification": "partage",
        "workspaces": ["copro", "admin-perso", "entreprise"]
    },
    {
        "name": "fiscal",
        "classification": "partage",
        "workspaces": ["finances-perso", "entreprise"]
    },
    {
        "name": "templates",
        "classification": "partage",
        "workspaces": ["dev", "consulting", "entreprise"]
    }
]

# Fonds documentaire initial représentatif
DOCUMENTS_SPEC = [
    # 1. finances-perso
    {
        "workspace": "finances-perso",
        "collection": "Comptes & Relevés Bancaires",
        "title": "Relevé Bancaire Compte Courant BNP - Janvier 2026",
        "scope": "finances",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "BNP PARIBAS - RELEVÉ DE COMPTE COURANT PERSONNEL\n"
            "Titulaire : Compte Principal Alexandre | Période : 01/01/2026 au 31/01/2026\n"
            "Solde au 01/01/2026 : 3 450,20 EUR\n"
            "--------------------------------------------------------------------------------\n"
            "Opérations du mois :\n"
            "- 05/01/2026 : Virement Salaire/Recette Client : + 3 800,00 EUR\n"
            "- 08/01/2026 : Prélèvement EDF Énergie : - 142,50 EUR\n"
            "- 12/01/2026 : Prélèvement Assurance Habitation MAIF : - 38,20 EUR\n"
            "- 15/01/2026 : Appel de charges Copropriété T1 2026 : - 420,00 EUR\n"
            "- 20/01/2026 : Abonnement Internet Fibre : - 39,90 EUR\n"
            "- 28/01/2026 : Virement Épargne Livret A : - 1 500,00 EUR\n"
            "--------------------------------------------------------------------------------\n"
            "Solde créditeur au 31/01/2026 : 5 109,60 EUR"
        )
    },
    {
        "workspace": "finances-perso",
        "collection": "Fiscalité Personnelle (Avis IRPP & Taxes)",
        "title": "Avis d'Impôt sur le Revenu 2025 (Revenus 2024)",
        "scope": "finances",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "RÉPUBLIQUE FRANÇAISE - DIRECTION GÉNÉRALE DES FINANCES PUBLIQUES\n"
            "AVIS D'IMPÔT 2025 SUR LES REVENUS DE L'ANNÉE 2024\n"
            "Numéro fiscal déclarant : 18 45 90 23 88 12\n"
            "Revenu brut global déclaré : 48 200,00 EUR\n"
            "Déductions forfaitaires pour frais professionnels (10%) : - 4 820,00 EUR\n"
            "Revenu net imposable : 43 380,00 EUR (Nombre de parts : 1)\n"
            "Montant de l'impôt net calculé : 3 860,00 EUR\n"
            "Retenue à la source prélevée en 2024 : 3 860,00 EUR\n"
            "Solde d'impôt net restant à payer : 0,00 EUR (Situation en règle)\n"
            "Taux de prélèvement à la source actualisé : 8,9%"
        )
    },
    {
        "workspace": "finances-perso",
        "collection": "Fiscalité Personnelle (Avis IRPP & Taxes)",
        "title": "Avis de Taxe Foncière 2025 - Résidence Principale Marseille",
        "scope": "finances",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "AVIS DE TAXE FONCIÈRE 2025 SUR LES PROPRIÉTÉS BÂTIES\n"
            "Adresse du bien : 12 Rue des Fleurs, 13000 Marseille (Appartement Lot 42)\n"
            "Base d'imposition communale (Valeur locative cadastrale nette) : 3 450 EUR\n"
            "Cotisation communale et intercommunale : 1 245,00 EUR\n"
            "Taxe d'enlèvement des ordures ménagères (TEOM) : 210,00 EUR\n"
            "Total net de taxe foncière à régler : 1 455,00 EUR\n"
            "Paiement par prélèvement automatique à l'échéance du 15 octobre 2025."
        )
    },

    # 2. admin-perso
    {
        "workspace": "admin-perso",
        "collection": "Assurances & Logement",
        "title": "Contrat Assurance Multirisque Habitation - MAIF 2026",
        "scope": "admin",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "MAIF ASSURANCES - CONTRAT MULTIRISQUE HABITATION 'RAQVAM'\n"
            "Numéro de sociétaire / Police : 78451290-A | Période d'effet : 01/01/2026 au 31/12/2026\n"
            "Bien assuré : Résidence Principale, 12 Rue des Fleurs, 13000 Marseille (4 pièces)\n"
            "Garanties incluses :\n"
            "• Responsabilité civile vie privée et occupant : Couverture illimitée\n"
            "• Incendie, explosion, événements climatiques : Franchise 150 EUR\n"
            "• Dégât des eaux et gel : Franchise 120 EUR\n"
            "• Vol, vandalisme et bris de glaces : Capital mobilier garanti 50 000 EUR\n"
            "• Protection juridique étendue liée au logement\n"
            "Cotisation annuelle forfaitaire : 458,40 EUR TTC (soit 38,20 EUR / mois)"
        )
    },
    {
        "workspace": "admin-perso",
        "collection": "Identité & État Civil",
        "title": "Certificat d'Immatriculation Véhicule (Carte Grise)",
        "scope": "admin",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "MINISTÈRE DE L'INTÉRIEUR - CERTIFICAT D'IMMATRICULATION\n"
            "Numéro d'immatriculation : AA-123-BB | Date de 1ère mise en circulation : 14/06/2021\n"
            "Titulaire : M. Alexandre Garcia | Domicile : 12 Rue des Fleurs, 13000 Marseille\n"
            "Marque : Peugeot | Modèle : 208 PureTech 100 S&S | Carburant : Essence (ES)\n"
            "Puissance administrative (CV) : 5 | Taux d'émission CO2 : 115 g/km (Crit'Air 1)\n"
            "Contrôle technique : Dernier contrôle valide jusqu'au 14/06/2027."
        )
    },

    # 3. sante-perso
    {
        "workspace": "sante-perso",
        "collection": "Analyses & Prescriptions",
        "title": "Ordonnance Médicale - Traitement Allergique Saisonnier",
        "scope": "owner",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "CABINET MÉDICAL DU DR. MARTIN - MÉDECINE GÉNÉRALE\n"
            "Patient : Alexandre Garcia | Date : 15/03/2026\n"
            "PRESCRIPTION MÉDICALE :\n"
            "1. Lévocétirizine 5 mg comprimés : 1 comprimé le soir au coucher pendant 30 jours (rhinite saisonnière aux pollens de cyprès).\n"
            "2. Flixonase spray nasal (fluticasone) : 1 pulvérisation dans chaque narine le matin pendant 1 mois.\n"
            "3. Dosages sanguins IgE spécifiques si persistance des symptômes.\n"
            "Ordonnance non renouvelable sans réévaluation clinique."
        )
    },
    {
        "workspace": "sante-perso",
        "collection": "Dossier Médical",
        "title": "Carnet de Santé & Rappel Vaccinal DTP 2025",
        "scope": "owner",
        "sensitivity": "secret",
        "status": "actif",
        "content": (
            "HISTORIQUE MÉDICAL PERSONNEL - STRICTEMENT SECRET\n"
            "Patient : Alexandre Garcia | Né en 1985\n"
            "Vaccination Diphtérie-Tétanos-Poliomyélite (DTP) :\n"
            "• Dernier rappel d'adulte effectué le 15/09/2025 par le Dr. Martin.\n"
            "• Lot vaccin : REPEVAX-A48291B.\n"
            "• Prochain rappel décennal préconisé en 2045 (à 60 ans selon le calendrier vaccinal officiel).\n"
            "Antécédents chirurgicaux : Appendicectomie sous cœlioscopie en 2012 sans complication.\n"
            "Allergies connues : Pollens d'arbres (cyprès, platane), pas d'allergie médicamenteuse identifiée."
        )
    },

    # 4. entreprise
    {
        "workspace": "entreprise",
        "collection": "Facturation & Devis",
        "title": "Facture Prestation Logicielle FACT-2026-001 - Client TechSolutions",
        "scope": "pro",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "ENTREPRISE INDIVIDUELLE ALEXANDRE GARCIA (CONSULTING LOGICIEL)\n"
            "SIREN : 912 345 678 | NAF : 6202A (Conseil en systèmes et logiciels informatiques)\n"
            "FACTURE N° FACT-2026-001 | Date d'émission : 31/01/2026\n"
            "Client : SAS TechSolutions, 45 Boulevard de l'Innovation, 75008 Paris\n"
            "Objet : Conception et déploiement d'une architecture RAG d'entreprise sécurisée\n"
            "Détail des prestations :\n"
            "• Analyse d'architecture et design pgvector : 5 jours x 700 EUR = 3 500,00 EUR HT\n"
            "• Implémentation du pipeline de chunking et connecteurs : 3 jours x 700 EUR = 2 100,00 EUR HT\n"
            "• Tests de résilience et durcissement Traefik : 2 jours x 700 EUR = 1 400,00 EUR HT\n"
            "Total Hors Taxes : 7 000,00 EUR HT\n"
            "TVA (20,0%) : 1 400,00 EUR\n"
            "Net à payer TTC : 8 400,00 EUR\n"
            "Conditions de règlement : Virement bancaire sous 30 jours fin de mois."
        )
    },
    {
        "workspace": "entreprise",
        "collection": "Déclarations & Cotisations URSSAF",
        "title": "Attestation de Déclaration Trimestrielle URSSAF T4 2025",
        "scope": "pro",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "URSSAF PROVENCE-ALPES-CÔTE D'AZUR - DÉCLARATION DE REVENUS\n"
            "Compte cotisant : 130 9823412098 | Période : 4ème trimestre 2025 (Oct-Déc 2025)\n"
            "Chiffre d'affaires prestations de services BNC déclaré : 22 500,00 EUR\n"
            "Taux de cotisations sociales obligatoire : 21,20%\n"
            "Contribution à la Formation Professionnelle (CFP) : 0,20%\n"
            "Montant total des cotisations prélevées : 4 815,00 EUR\n"
            "Statut du prélèvement : Payé par télérèglement SEPA le 31/01/2026.\n"
            "Attestation de régularité fiscale et sociale disponible en ligne."
        )
    },

    # 5. dev
    {
        "workspace": "dev",
        "collection": "Documentation Technique & Architecture",
        "title": "Architecture & Spécification du Moteur RAG MEMENTOMORI",
        "scope": "dev",
        "sensitivity": "interne",
        "status": "actif",
        "content": (
            "# MEMENTOMORI — Architecture du Moteur RAG Hybride Multi-Workspaces\n"
            "1. Pipeline d'ingestion :\n"
            "   - Découpage structurel et sémantique (Chunking hybride avec fenêtres de 400-800 tokens et recouvrement).\n"
            "   - Calcul des embeddings via BAAI/bge-m3 (dimension 1024) ou fallback mock déterministe.\n"
            "   - Indexation plein texte PostgreSQL tsvector 'french' avec dictionnaire désaccentué.\n"
            "2. Pipeline de recherche hybride :\n"
            "   - Double extraction : 20 hits distance cosinus pgvector + 20 hits FTS ts_rank.\n"
            "   - Fusion RRF (Reciprocal Rank Fusion) avec k=60 et boost lexical de 3.0 sur le FTS.\n"
            "   - Reranker contextuel cross-encoder combinant densité lexicale, proximité et alignement de préfixe.\n"
            "3. Sécurité et cloisonnement :\n"
            "   - Triple filtrage SQL systématique : workspace_id -> allowed_scopes -> max_sensitivity.\n"
            "   - Éviction garantie des modèles LLM Cloud pour tout fragment portant le statut 'secret'."
        )
    },
    {
        "workspace": "dev",
        "collection": "Documentation Technique & Architecture",
        "title": "Guide de Durcissement Traefik, Docker Socket Proxy & Cloudflare",
        "scope": "dev",
        "sensitivity": "interne",
        "status": "actif",
        "content": (
            "# Guide de Déploiement Sécurisé — Cluster MEMENTOMORI\n"
            "1. Tunnel Cloudflare Zero Trust (cloudflared) :\n"
            "   - 4 connexions QUIC chiffrées sortantes vers le point d'échange Paris.\n"
            "   - Zéro port d'écoute ouvert sur la box Internet (ports 80 et 443 fermés, rejet immédiat des scans IP).\n"
            "   - En-tête de passerelle WAF obligatoire : X-Api-Gateway-Key avec rejet 403 des requêtes directes.\n"
            "2. Docker Socket Proxy (tecnativa/docker-socket-proxy) :\n"
            "   - Traefik accède au démon Docker via tcp://docker-socket-proxy:2375 au lieu du socket unix brut.\n"
            "   - Seules les requêtes GET sur les conteneurs et réseaux sont transmises ; les mutations POST/DELETE reçoivent un 403 Forbidden.\n"
            "3. Résilience et Sauvegardes :\n"
            "   - Sauvegarde automatisée nocturne à 03h00 (Dumps PostgreSQL, Redis RDB, tar Paperless, SQLite Kuma).\n"
            "   - Rétention Grand-Père / Père / Fils (7 jours, 4 semaines, 3 mois) avec chiffrement Fernet."
        )
    },

    # 6. formation
    {
        "workspace": "formation",
        "collection": "Cours & Certifications",
        "title": "Synthèse de Cours : Principes des Architectures Multi-Agents Résilientes",
        "scope": "formation",
        "sensitivity": "interne",
        "status": "actif",
        "content": (
            "# Systèmes Multi-Agents et Orchestration Autonome\n"
            "Principes directeurs pour des agents IA en production :\n"
            "1. Spécialisation et principe de moindre privilège :\n"
            "   Chaque sous-agent ne doit recevoir que le sous-ensemble de contexte documentaire strictement nécessaire à sa tâche.\n"
            "2. Découplage de la communication :\n"
            "   Communication asynchrone par échange de messages typés plutôt que par partages de mémoire globale modifiable.\n"
            "3. Mécanisme de fallback déterministe :\n"
            "   Si le modèle de raisonnement principal est indisponible ou dépasse son budget de latence, un modèle léger ou une recherche directe dégradée doit immédiatement prendre le relais.\n"
            "4. Vérification de Grounding post-génération :\n"
            "   Toute affirmation produite doit être vérifiée par projection d'entités contre les fragments sources avant restitution à l'utilisateur."
        )
    },
    {
        "workspace": "formation",
        "collection": "Fiches de Lecture & Synthèses",
        "title": "Fiche de Lecture : Designing Data-Intensive Applications (M. Kleppmann)",
        "scope": "formation",
        "sensitivity": "interne",
        "status": "actif",
        "content": (
            "# Fiche de Lecture — Designing Data-Intensive Applications\n"
            "Auteur : Martin Kleppmann | Sujets : Fiabilité, Évolutivité, Maintenabilité\n"
            "Points essentiels retenus :\n"
            "• Modèles de stockage : B-Trees (optimisés pour les lectures ponctuelles) vs LSM-Trees (optimisés pour le débit d'écriture séquentiel comme SSTables).\n"
            "• Réplication et Consensus : Algorithmes Raft et Paxos pour garantir un consensus en présence de partitions réseau. Différence fondamentale entre réplication synchrone et asynchrone.\n"
            "• Niveaux d'isolation transactionnelle : Read Committed, Snapshot Isolation (MVCC comme PostgreSQL) et Sérialisabilité.\n"
            "• Systèmes dérivés : L'importance d'utiliser les logs d'événements (CDC) pour alimenter les index de recherche secondaire et les caches sans risque d'incohérence à long terme."
        )
    },

    # 7. consulting
    {
        "workspace": "consulting",
        "collection": "Propositions Commerciales",
        "title": "Proposition d'Intervention : Audit Technique & Stratégie RAG Sécurisé",
        "scope": "consulting",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "# PROPOSITION COMMERCIALE & CADRAGE DE MISSION\n"
            "Client ciblé : Entreprises de taille intermédiaire / Direction des Systèmes d'Information\n"
            "Objectif : Déployer une base de connaissances d'entreprise confidentielle avec RAG souverain.\n"
            "Périmètre de la mission (15 jours ouvrés) :\n"
            "1. Phase 1 - Cadrage documentaire & cartographie des sensibilités (3 jours).\n"
            "2. Phase 2 - Choix d'architecture et benchmarks de modèles d'embeddings (4 jours).\n"
            "3. Phase 3 - Implémentation du moteur de recherche hybride et filtrage RBAC (5 jours).\n"
            "4. Phase 4 - Validation de la sécurité, tests de charge et formation des équipes (3 jours).\n"
            "Budget forfaitaire proposé : 10 500,00 EUR HT."
        )
    },
    {
        "workspace": "consulting",
        "collection": "Missions & Livrables Clients",
        "title": "Livrable d'Audit : Recommandations Sécurité & Partitionnement PostgreSQL",
        "scope": "consulting",
        "sensitivity": "confidentiel",
        "status": "actif",
        "content": (
            "# RAPPORT D'AUDIT TECHNIQUE — RECOMMANDATIONS BASES DE DONNÉES\n"
            "Client : FinTech Solutions | Mission d'optimisation base de données\n"
            "Constats et Recommandations clés :\n"
            "1. Indexation pgvector : Recommandation d'adopter des index HNSW (Hierarchical Navigable Small World) avec m=16 et ef_construction=64 pour des requêtes de similarité sous 5 ms.\n"
            "2. Ségrégation des charges de travail : Séparer les transactions OLTP des recherches vectorielles lourdes à l'aide de réplicas en lecture PostgreSQL avec streaming logique.\n"
            "3. Durcissement des connexions : Forcer le chiffrement SSL/TLS avec certificats vérifiés et pooler les connexions via PgBouncer en mode transaction pour absorber les pics de charge."
        )
    },

    # 8. veille
    {
        "workspace": "veille",
        "collection": "Veille Technologique & IA",
        "title": "Synthèse de Veille : Modèles d'Embeddings Multilingues et Rerankers 2026",
        "scope": "veille",
        "sensitivity": "interne",
        "status": "actif",
        "content": (
            "# RADAR TECHNOLOGIQUE — ÉVOLUTION DU RAG EN 2026\n"
            "1. Modèles d'embeddings denses et clairsemés :\n"
            "   Le modèle BAAI/bge-m3 confirme sa supériorité en environnement multilingue (français/anglais) avec support natif d'entrées jusqu'à 8192 tokens et fusion interne Dense + Sparse Lexical.\n"
            "2. Montée en puissance des Rerankers légers :\n"
            "   L'utilisation d'un Cross-Encoder en deuxième étape de classement apporte un gain de 15% à 25% de précision (MRR@10) par rapport à un classement vectoriel ou BM25 seul, pour une surconsommation CPU minime (< 10 ms par requête).\n"
            "3. Inférence locale et souveraine :\n"
            "   Les modèles quantifiés 4-bit (GGUF) sous Ollama/vLLM permettent de traiter des documents confidentiels sur des cartes graphiques grand public (16-24 Go VRAM) avec une fidélité équivalente aux API cloud propriétaires."
        )
    },
    {
        "workspace": "veille",
        "collection": "Veille Réglementaire & Normes",
        "title": "Veille Réglementaire : Entrée en Vigueur de l'AI Act Européen",
        "scope": "veille",
        "sensitivity": "interne",
        "status": "a_verifier",  # Sas d'ingestion à vérifier
        "content": (
            "# VEILLE RÉGLEMENTAIRE — RÈGLEMENT EUROPÉEN SUR L'INTELLIGENCE ARTIFICIELLE (AI ACT)\n"
            "Statut du document : Reçu pour validation dans le sas d'ingestion de veille.\n"
            "Points d'attention pour les applications de gestion des connaissances d'entreprise :\n"
            "1. Classification du risque : Les systèmes de RAG d'aide à la décision interne sont généralement classés à risque faible ou modéré, mais requièrent une transparence obligatoire sur la nature générative des réponses.\n"
            "2. Gouvernance des données : Obligation de traçabilité des données d'entraînement et d'indexation, nécessitant un journal d'audit rigoureux (Audit Log) consignant les sources et dates d'ingestion.\n"
            "3. Protection de la vie privée : Interdiction formelle d'apprentissage non consenti sur des données personnelles non anonymisées."
        )
    },

    # 9. Collections transversales partagées (Many-to-Many)
    {
        "workspace": "copro",
        "collection": "juridique-general",
        "title": "Code Civil — Extraits Régime de la Propriété & des Contrats (Art. 544 et 1101)",
        "scope": "public",
        "sensitivity": "public",
        "status": "actif",
        "content": (
            "RÉPUBLIQUE FRANÇAISE — CODE CIVIL (DISPOSITIONS FONDAMENTALES)\n"
            "Article 544 :\n"
            "La propriété est le droit de jouir et disposer des choses de la manière la plus absolue, pourvu qu'on n'en fasse pas un usage prohibé par les lois ou par les règlements.\n"
            "Article 1101 :\n"
            "Le contrat est un accord de volontés entre deux ou plusieurs personnes destiné à créer, modifier, transmettre ou éteindre des obligations.\n"
            "Application : Ce cadre juridique général régit les relations contractuelles entre copropriétaires, locataires, prestataires de services et entreprises."
        )
    },
    {
        "workspace": "finances-perso",
        "collection": "fiscal",
        "title": "Barème de l'Impôt sur le Revenu 2026 & Plafonds Fiscaux Déductibles",
        "scope": "public",
        "sensitivity": "interne",
        "status": "actif",
        "content": (
            "MINISTÈRE DE L'ÉCONOMIE ET DES FINANCES — SYNTHÈSE FISCALE 2026\n"
            "Tranches d'imposition sur le revenu net global (pour une part fiscale) :\n"
            "• Jusqu'à 11 294 EUR : 0%\n"
            "• De 11 295 EUR à 28 797 EUR : 11%\n"
            "• De 28 798 EUR à 82 341 EUR : 30%\n"
            "• De 82 342 EUR à 177 106 EUR : 41%\n"
            "• Plus de 177 106 EUR : 45%\n"
            "Plafond d'abattement forfaitaire pour frais professionnels : 14 171 EUR.\n"
            "Plafond des versements déductibles sur Plan d'Épargne Retraite (PER) individuel : 10% des revenus professionnels."
        )
    },
    {
        "workspace": "dev",
        "collection": "templates",
        "title": "Modèle Universel de Contrat de Prestation et Conditions Générales de Service",
        "scope": "public",
        "sensitivity": "interne",
        "status": "actif",
        "content": (
            "# MODÈLE TYPE — CONTRAT DE PRESTATION DE SERVICES INTELLECTUELS\n"
            "Entre le Prestataire et le Client :\n"
            "1. Objet du contrat : Définition précise de la mission, livrables attendus, critères d'acceptation et calendrier de réalisation.\n"
            "2. Obligations des parties : Le prestataire est tenu à une obligation de moyens renforcée. Le client s'engage à fournir les accès et informations nécessaires.\n"
            "3. Propriété intellectuelle : Cession des droits d'exploitation patrimoniaux sur les livrables finals sous réserve du paiement intégral du prix convenu.\n"
            "4. Confidentialité : Engagement réciproque de non-divulgation des informations sensibles, secrets d'affaires et données techniques pendant une durée de 3 ans après la fin de la mission."
        )
    }
]


async def setup_all_workspaces():
    print("=" * 70)
    print("MEMENTOMORI — Déploiement et Remplissage des 8 Workspaces Cibles (Sprint 12)")
    print("=" * 70)

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # 1. Résolution des Principals
        p_res = await session.execute(select(Principal))
        principals_by_ext = {p.external_id: p for p in p_res.scalars().all()}
        admin_user = principals_by_ext.get("admin_user")
        if not admin_user:
            admin_user = Principal(type="user", external_id="admin_user", display_name="Cabinet Mer & Soleil (Admin)")
            session.add(admin_user)
            await session.flush()
            principals_by_ext["admin_user"] = admin_user

        # 2. Déploiement des 8 Workspaces
        workspaces_by_slug: Dict[str, Workspace] = {}
        all_ws_res = await session.execute(select(Workspace))
        for w in all_ws_res.scalars().all():
            workspaces_by_slug[w.slug] = w

        for ws_spec in WORKSPACES_SPEC:
            slug = ws_spec["slug"]
            ws = workspaces_by_slug.get(slug)
            if not ws:
                ws = Workspace(
                    name=ws_spec["name"],
                    slug=slug,
                    domain=ws_spec["domain"],
                    settings=ws_spec["settings"]
                )
                session.add(ws)
                await session.flush()
                workspaces_by_slug[slug] = ws
                print(f" [+] Workspace créé : {ws_spec['name']} (slug='{slug}', domain='{ws_spec['domain']}')")
            else:
                print(f" [=] Workspace existant : {ws.name} (slug='{slug}')")

            # Création de la source manuelle par défaut pour ce workspace
            src_res = await session.execute(
                select(Source).where(Source.workspace_id == ws.id, Source.connector_type == "manual")
            )
            src = src_res.scalar_one_or_none()
            if not src:
                src = Source(workspace_id=ws.id, connector_type="manual", auto_approve=True)
                session.add(src)
                await session.flush()

            # Attribution de la politique de sécurité (sante-perso est réservé à sante_user)
            if slug != "sante-perso":
                pol_res = await session.execute(
                    select(Policy).where(Policy.workspace_id == ws.id, Policy.principal_id == admin_user.id)
                )
                pol = pol_res.scalar_one_or_none()
                if not pol:
                    pol = Policy(
                        workspace_id=ws.id,
                        principal_id=admin_user.id,
                        role="owner",
                        allowed_scopes=["owner", "public", "copro", "finances", "admin", "sante", "pro", "dev", "consulting", "formation", "veille"],
                        actions=["read", "write", "search", "admin"],
                        max_sensitivity="secret"
                    )
                    session.add(pol)
                    await session.flush()
                    print(f"     [+] Policy 'owner' attribuée à admin_user sur '{slug}'")

            # Création des collections dédiées au workspace
            for col_spec in ws_spec["collections"]:
                col_name = col_spec["name"]
                col_class = col_spec["classification"]
                col_res = await session.execute(
                    select(Collection).where(Collection.name == col_name)
                )
                col = col_res.scalar_one_or_none()
                if not col:
                    col = Collection(name=col_name, classification=col_class)
                    session.add(col)
                    await session.flush()
                    print(f"     [+] Collection créée : '{col_name}' ({col_class})")

                # Liaison Collection <-> Workspace
                link_res = await session.execute(
                    select(CollectionWorkspace).where(
                        CollectionWorkspace.collection_id == col.id,
                        CollectionWorkspace.workspace_id == ws.id
                    )
                )
                if not link_res.scalar_one_or_none():
                    session.add(CollectionWorkspace(collection_id=col.id, workspace_id=ws.id))
                    await session.flush()
                    print(f"         [+] Liaison établie : '{col_name}' <-> '{slug}'")

        # 3. Déploiement des Collections Transversales Partagées (Many-to-Many)
        print("\n--- Collections Transversales Partagées (Many-to-Many) ---")
        for shared_spec in SHARED_COLLECTIONS_SPEC:
            col_name = shared_spec["name"]
            col_class = shared_spec["classification"]
            col_res = await session.execute(select(Collection).where(Collection.name == col_name))
            col = col_res.scalar_one_or_none()
            if not col:
                col = Collection(name=col_name, classification=col_class)
                session.add(col)
                await session.flush()
                print(f" [+] Collection partagée créée : '{col_name}' ({col_class})")
            else:
                print(f" [=] Collection partagée existante : '{col_name}'")

            for ws_slug in shared_spec["workspaces"]:
                ws = workspaces_by_slug.get(ws_slug)
                if ws:
                    link_res = await session.execute(
                        select(CollectionWorkspace).where(
                            CollectionWorkspace.collection_id == col.id,
                            CollectionWorkspace.workspace_id == ws.id
                        )
                    )
                    if not link_res.scalar_one_or_none():
                        session.add(CollectionWorkspace(collection_id=col.id, workspace_id=ws.id))
                        await session.flush()
                        print(f"     [+] Liaison multilatérale : '{col_name}' <-> '{ws_slug}'")

        await session.commit()

        # 4. Ingestion et Indexation Vectorielle des Documents Pilotes
        print("\n--- Ingestion et Indexation des Documents Représentatifs ---")
        total_indexed = 0
        total_skipped = 0

        for doc_spec in DOCUMENTS_SPEC:
            ws_slug = doc_spec["workspace"]
            col_name = doc_spec["collection"]
            title = doc_spec["title"]
            scope = doc_spec["scope"]
            sens = doc_spec["sensitivity"]
            status = doc_spec.get("status", "actif")
            content = doc_spec["content"]

            ws = workspaces_by_slug.get(ws_slug)
            if not ws:
                print(f" [!] Workspace '{ws_slug}' introuvable, document ignoré.")
                continue

            col_res = await session.execute(select(Collection).where(Collection.name == col_name))
            col = col_res.scalar_one_or_none()
            if not col:
                print(f" [!] Collection '{col_name}' introuvable, document ignoré.")
                continue

            src_res = await session.execute(
                select(Source).where(Source.workspace_id == ws.id, Source.connector_type == "manual")
            )
            src = src_res.scalar_one_or_none()
            src_id = src.id if src else None

            # Vérification déduplication SHA-256
            is_dup, dup_id, reason = await check_duplicate(
                content=content,
                db=session,
                source_id=src_id,
                collection_id=col.id
            )
            if is_dup:
                print(f" [=] Document existant dédupliqué (SHA-256) : '{title}' (doc_id={dup_id})")
                total_skipped += 1
                continue

            # Création du document
            c_hash = compute_content_hash(content)
            doc = Document(
                collection_id=col.id,
                source_id=src_id,
                title=title,
                status=status,
                scope=scope,
                sensitivity=sens,
                content_hash=c_hash,
                is_active=True,
                version=1,
                metadata_={"workspace_slug": ws_slug, "classification": col.classification}
            )
            session.add(doc)
            await session.flush()

            doc_version = DocumentVersion(
                document_id=doc.id,
                version_number=1,
                original_file_ref=f"manual://{ws_slug}/{title}",
                extracted_text=content
            )
            session.add(doc_version)
            await session.flush()

            # Chunking hybride & Embeddings
            chunks = split_into_chunks(text=content, document_title=title, workspace_slug=ws_slug)
            for idx, ch in enumerate(chunks):
                emb = await generate_embedding(ch.content)
                frag = Fragment(
                    document_version_id=doc_version.id,
                    chunk_index=idx,
                    page_number=ch.page_number or 1,
                    content=ch.content,
                    embedding=emb,
                    context_prefix=ch.context_prefix or f"{ws.name} > {col.name}",
                    citation_ref={"document_title": title, "page": ch.page_number or 1}
                )
                session.add(frag)

            await session.commit()
            total_indexed += 1
            print(f" [+] Document indexé avec succès : '{title}' ({len(chunks)} fragments) -> {ws_slug}")

        print("\n" + "=" * 70)
        print(f"RÉSUMÉ DU DÉPLOIEMENT DU SPRINT 12 :")
        print(f" • 9 Workspaces opérationnels : copro, finances-perso, admin-perso, sante-perso, entreprise, dev, formation, consulting, veille")
        print(f" • 3 Collections partagées transversales : juridique-general, fiscal, templates")
        print(f" • Documents indexés : {total_indexed} nouveaux, {total_skipped} préexistants dédupliqués")
        print("=" * 70)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(setup_all_workspaces())
