"""Service de Reranking Cross-Encoder pour affiner le classement RRF (§16.6, §17 B12)."""

from __future__ import annotations
import math
import re
from typing import List, Optional, TYPE_CHECKING
from knowledge.logging import get_logger

if TYPE_CHECKING:
    from knowledge.services.search import SearchResult

logger = get_logger(__name__)

STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "au", "aux",
    "et", "ou", "mais", "donc", "or", "ni", "car", "pour", "dans", "par",
    "sur", "sous", "vers", "avec", "sans", "chez", "ce", "cet", "cette", "ces",
    "est", "sont", "ete", "etre", "avoir", "quel", "quelle", "quels", "quelles",
    "qui", "que", "quoi", "dont", "comment", "combien", "pourquoi", "quand"
}


def tokenize(text: str) -> List[str]:
    """Découpe un texte en mots normalisés minuscules sans ponctuation."""
    return [
        t for t in re.findall(r"\b[a-zA-Z0-9_\u00C0-\u017F]{2,}\b", text.lower())
        if t not in STOP_WORDS
    ]


def compute_cross_score(query: str, fragment_text: str, context_prefix: Optional[str] = None) -> float:
    """
    Calcule un score de pertinence croisée (Cross-Scoring) entre la question et le texte du fragment :
    - Correspondance d'expressions exactes
    - Densité et couverture des termes de la question
    - Proximité spatiale des occurrences de mots-clés
    - Alignement thématique avec le titre/section (context_prefix)
    """
    clean_q = query.strip().lower()
    full_text = (f"{context_prefix or ''} {fragment_text}").lower()
    q_tokens = tokenize(clean_q)

    if not q_tokens:
        return 0.5

    # 1. Correspondance d'expression exacte (Exact phrase match bonus)
    phrase_score = 0.0
    if len(q_tokens) >= 2 and clean_q in full_text:
        phrase_score = 1.0
    elif len(q_tokens) >= 3:
        # Sous-expressions de 2 mots
        sub_phrases = [" ".join(q_tokens[i:i+2]) for i in range(len(q_tokens)-1)]
        matched_subs = sum(1 for sp in sub_phrases if sp in full_text)
        phrase_score = matched_subs / len(sub_phrases)

    # 2. Couverture pondérée des termes (Term overlap & IDF proxy)
    term_weights = {t: math.log(1.0 + len(t)) for t in q_tokens}
    total_weight = sum(term_weights.values()) or 1.0

    matched_weight = sum(
        term_weights[t] for t in q_tokens
        if re.search(rf"\b{re.escape(t)}\b", full_text)
    )
    coverage_score = matched_weight / total_weight

    # 3. Alignement avec le titre de section / préfixe contextuel
    prefix_score = 0.0
    if context_prefix:
        prefix_lower = context_prefix.lower()
        matched_in_prefix = sum(1 for t in q_tokens if t in prefix_lower)
        prefix_score = matched_in_prefix / len(q_tokens)

    # 4. Proximité des mots-clés (termes apparaissant à courte distance)
    proximity_score = 0.0
    positions = []
    for t in q_tokens:
        match = re.search(rf"\b{re.escape(t)}\b", full_text)
        if match:
            positions.append(match.start())

    if len(positions) >= 2:
        span = max(positions) - min(positions)
        # Plus le span est court (< 200 caractères), plus la proximité est forte
        proximity_score = max(0.0, 1.0 - (span / 400.0))

    # Combinaison linéaire pondérée
    cross_score = (
        0.35 * coverage_score +
        0.30 * phrase_score +
        0.20 * proximity_score +
        0.15 * prefix_score
    )

    return min(1.0, max(0.0, cross_score))


async def rerank_candidates(
    query: str,
    candidates: List[SearchResult],
    top_k: int = 5,
    blend_weight: float = 0.60,
) -> List[SearchResult]:
    """
    Reranke les candidats issus de la fusion RRF (§16.6, B12).
    Combine le score RRF initial avec le cross-score contextuel fin.
    """
    if not candidates:
        return []

    # Normalisation des scores RRF initiaux (min-max)
    max_rrf = max((c.score for c in candidates), default=1.0) or 1.0

    scored_candidates = []
    for c in candidates:
        norm_rrf = c.score / max_rrf
        cross_sc = compute_cross_score(query, c.content, c.context_prefix)
        # Score final combiné : blend_weight * cross_sc + (1 - blend_weight) * norm_rrf
        final_score = round((blend_weight * cross_sc) + ((1.0 - blend_weight) * norm_rrf), 5)
        
        # Mettre à jour le score du SearchResult
        c.score = final_score
        scored_candidates.append(c)

    # Re-tri décroissant par score final
    scored_candidates.sort(key=lambda x: x.score, reverse=True)
    results = scored_candidates[:top_k]

    logger.info(
        "reranking_completed",
        query=query[:60],
        initial_candidates=len(candidates),
        returned_top_k=len(results),
        top_score=results[0].score if results else 0.0,
    )

    return results
