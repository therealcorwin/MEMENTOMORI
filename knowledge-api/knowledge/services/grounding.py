"""Service de vérification de grounding post-LLM et détection d'hallucinations (§17 B11)."""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING
from knowledge.logging import get_logger

if TYPE_CHECKING:
    from knowledge.services.search import SearchResult

logger = get_logger(__name__)

# Expressions régulières pour extraire les entités factuelles sensibles
PATTERNS = {
    # Montants monétaires : 150 €, 1 250,50 euros, 45k€
    "amount": re.compile(
        r"\b\d+(?:[\s.,]\d+)?\s*(?:€|euros?|k€|centimes?)(?!\w)",
        re.IGNORECASE,
    ),
    # Pourcentages : 15%, 2.5 %
    "percentage": re.compile(r"\b\d+(?:[.,]\d+)?\s*%(?!\w)"),
    # Lots et bâtiments : lot 42, lots 12 et 14, bâtiment B, escalier A
    "lot_or_building": re.compile(
        r"\b(?:lots?|bâtiments?|batiments?|escaliers?|étages?)\s+[A-Za-z0-9_-]+\b",
        re.IGNORECASE,
    ),
    # Articles juridiques et règlements : article 24, art. 10
    "article": re.compile(
        r"\b(?:articles?|art\.)\s+[0-9]+(?:-[0-9]+)?\b",
        re.IGNORECASE,
    ),
    # Dates formelles et années : 15/03/2024, 2024, 1er janvier 2023
    "date_or_year": re.compile(
        r"\b(?:(?:19|20)\d{2}|\d{1,2}[/-]\d{1,2}[/-](?:19|20)?\d{2})\b"
    ),
}


@dataclass
class GroundingVerificationResult:
    grounding_score: float
    total_entities: int
    verified_entities: List[str] = field(default_factory=list)
    unverified_entities: List[str] = field(default_factory=list)
    is_grounded: bool = True
    warning: Optional[str] = None


def normalize_token(text: str) -> str:
    """Normalise une chaîne pour comparaison souple (espaces, ponctuation, minuscules)."""
    text = text.lower().replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_factual_entities(text: str) -> List[str]:
    """Extrait toutes les entités factuelles clés de la réponse."""
    entities: List[str] = []
    seen = set()

    for category, pattern in PATTERNS.items():
        matches = pattern.findall(text)
        for m in matches:
            norm = normalize_token(m)
            if norm and norm not in seen:
                # Éviter de capturer des nombres isolés triviaux sans contexte
                if norm in ("1", "2", "3", "0"):
                    continue
                seen.add(norm)
                entities.append(norm)

    return entities


def verify_grounding(
    answer: str,
    fragments: List[SearchResult],
    strict_threshold: float = 0.80,
) -> GroundingVerificationResult:
    """
    Vérifie la traçabilité des entités factuelles énoncées dans la réponse LLM
    vis-à-vis des fragments sources fournis (§17 B11).
    """
    if not fragments:
        return GroundingVerificationResult(
            grounding_score=1.0 if not answer.strip() else 0.0,
            total_entities=0,
            is_grounded=True if not answer.strip() else False,
            warning="Aucun fragment documentaire fourni pour valider la réponse." if answer.strip() else None,
        )

    # Concaténation et normalisation des textes sources
    source_corpus = " ".join(
        f"{f.document_title} {f.context_prefix or ''} {f.content}"
        for f in fragments
    )
    norm_source_corpus = normalize_token(source_corpus)

    # Extraction des entités factuelles dans la réponse générée
    entities = extract_factual_entities(answer)
    if not entities:
        # Aucune entité chiffrée ou identifiant strict : réponse déclarative pure
        return GroundingVerificationResult(
            grounding_score=1.0,
            total_entities=0,
            verified_entities=[],
            unverified_entities=[],
            is_grounded=True,
            warning=None,
        )

    verified: List[str] = []
    unverified: List[str] = []

    for entity in entities:
        # Recherche directe
        if entity in norm_source_corpus:
            verified.append(entity)
            continue

        # Recherche des chiffres bruts contenus dans l'entité
        # Ex: si l'entité est "1 250 €", chercher "1250" ou "1 250"
        digits_only = re.sub(r"\D", "", entity)
        if len(digits_only) >= 2 and digits_only in re.sub(r"\D", "", norm_source_corpus):
            verified.append(entity)
            continue

        unverified.append(entity)

    total = len(entities)
    verified_count = len(verified)
    score = round(verified_count / total, 3) if total > 0 else 1.0

    is_grounded = score >= strict_threshold and len(unverified) <= 1
    warning = None

    if not is_grounded:
        sample_unverified = ", ".join(f"'{u}'" for u in unverified[:3])
        warning = (
            f"Vérification de fidélité documentaire (B11) : {len(unverified)} élément(s) chiffré(s) ou clé(s) "
            f"n'ont pas pu être directement recoupés dans les sources ({sample_unverified})."
        )
        logger.warning(
            "grounding_check_failed",
            score=score,
            total=total,
            unverified=unverified,
        )
    else:
        logger.info("grounding_check_passed", score=score, total=total, verified=verified_count)

    return GroundingVerificationResult(
        grounding_score=score,
        total_entities=total,
        verified_entities=verified,
        unverified_entities=unverified,
        is_grounded=is_grounded,
        warning=warning,
    )
