"""
Service d'auto-reformulation adaptative pour la recherche hybride (Sprint 7, Tâche 7.8, B15 & §16.14).
Évalue la confiance des résultats et applique un retry intelligent en cas de score faible.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.services.search import hybrid_search, SearchResult
from knowledge.services.embedding import generate_embedding
from knowledge.services.llm_resilience import generate_with_fallback

logger = get_logger(__name__)


@dataclass
class SearchQuality:
    confidence: float     # Score de confiance 0.0 à 1.0
    top_score: float      # Meilleur score de similarité obtenu
    fragment_count: int   # Nombre de fragments retournés
    verdict: str          # "good" | "weak" | "empty"


def evaluate_search_quality(results: List[SearchResult]) -> SearchQuality:
    """Évalue la qualité et le niveau de confiance des résultats de recherche (§16.14)."""
    if not results:
        return SearchQuality(confidence=0.0, top_score=0.0, fragment_count=0, verdict="empty")

    scores = [r.score for r in results]
    top_score = max(scores) if scores else 0.0
    count = len(results)

    # Calcul calibré de la confiance globale
    # Top score pèse 60%, la moyenne du top-3 pèse 40%
    sorted_scores = sorted(scores, reverse=True)
    avg_top3 = sum(sorted_scores[:3]) / min(count, 3)
    confidence = min(1.0, max(0.0, (top_score * 0.6) + (avg_top3 * 0.4)))

    if confidence >= 0.50:
        verdict = "good"
    elif confidence >= 0.15:
        verdict = "weak"
    else:
        verdict = "empty"

    return SearchQuality(
        confidence=confidence,
        top_score=top_score,
        fragment_count=count,
        verdict=verdict
    )


async def reformulate_for_better_recall(question: str, quality: SearchQuality) -> str:
    """Demande au LLM de reformuler une question ambigüe pour améliorer le recall (§16.14)."""
    strategy = (
        "Enrichis la question avec des synonymes et termes techniques spécifiques"
        if quality.verdict == "weak"
        else "Élargis la question avec des termes plus généraux et conceptuels"
    )

    prompt = (
        f"La question suivante n'a pas trouvé de bons résultats "
        f"(score de confiance : {quality.confidence:.0%}).\n\n"
        f"Question originale : \"{question}\"\n\n"
        f"{strategy}. Reformule en UNE SEULE question alternative plus explicite.\n"
        f"Réponds UNIQUEMENT avec la question reformulée, sans ponctuation introductive ni guillemets."
    )

    try:
        reformulated, level, model = await generate_with_fallback(
            prompt=prompt,
            temperature=0.3,
            max_tokens=80
        )
        cleaned = reformulated.strip().strip('"').strip("'")
        if cleaned and len(cleaned) > 3:
            logger.info(
                "question_reformulated",
                original=question,
                reformulated=cleaned,
                previous_confidence=quality.confidence
            )
            return cleaned
    except Exception as e:
        logger.warning("reformulation_failed", error=str(e), question=question)

    return question


async def adaptive_hybrid_search(
    query: str,
    workspace_ids: List[uuid.UUID],
    allowed_scopes: List[str],
    max_sensitivity: str,
    db: AsyncSession,
    top_k: int = 5,
    max_retries: int = 1,
) -> Tuple[List[SearchResult], str, SearchQuality]:
    """
    Exécute une recherche hybride avec auto-reformulation adaptative si les résultats sont faibles.
    Retourne (results, final_query, quality).
    """
    # 1. Tentative initiale avec la requête originale
    emb = await generate_embedding(query, task_type="RETRIEVAL_QUERY")
    results = await hybrid_search(
        query=query,
        query_embedding=emb,
        workspace_ids=workspace_ids,
        allowed_scopes=allowed_scopes,
        max_sensitivity=max_sensitivity,
        db=db,
        top_k=top_k,
    )

    quality = evaluate_search_quality(results)

    # Si les résultats sont satisfaisants ou retries désactivés, retourner directement
    if quality.verdict == "good" or max_retries <= 0:
        return results, query, quality

    # 2. Résultats faibles (weak) -> Reformulation et nouvel essai
    logger.info("adaptive_search_triggered_retry", query=query, confidence=quality.confidence)
    reformulated = await reformulate_for_better_recall(query, quality)

    if reformulated.lower() == query.lower():
        # Pas de meilleure suggestion
        return results, query, quality

    # Re-vectoriser et ré-exécuter
    new_emb = await generate_embedding(reformulated, task_type="RETRIEVAL_QUERY")
    new_results = await hybrid_search(
        query=reformulated,
        query_embedding=new_emb,
        workspace_ids=workspace_ids,
        allowed_scopes=allowed_scopes,
        max_sensitivity=max_sensitivity,
        db=db,
        top_k=top_k,
    )

    new_quality = evaluate_search_quality(new_results)

    # Si la reformulation a amélioré la confiance ou le nombre de résultats, retenir la nouvelle
    if new_quality.confidence > quality.confidence:
        logger.info(
            "adaptive_search_improved",
            original_conf=quality.confidence,
            new_conf=new_quality.confidence,
            reformulated=reformulated
        )
        return new_results, reformulated, new_quality
    else:
        logger.info(
            "adaptive_search_retained_original",
            original_conf=quality.confidence,
            new_conf=new_quality.confidence
        )
        return results, query, quality
