"""Tests de validation du service de Reranking Cross-Encoder (§16.6, §17 B12)."""

import pytest
import uuid
from knowledge.services.search import SearchResult
from knowledge.services.reranker import compute_cross_score, rerank_candidates


def create_candidate(title: str, content: str, score: float, section: str = "") -> SearchResult:
    return SearchResult(
        fragment_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        version=1,
        content=content,
        context_prefix=f"[Document: {title} | Section: {section}]" if section else None,
        page_number=1,
        score=score,
        citation_ref={"title": title},
        sensitivity="interne",
        scope="copro",
    )


def test_compute_cross_score():
    query = "horaires des travaux"
    
    # Fragment très pertinent avec expression exacte
    frag_exact = "Les horaires des travaux sont autorisés de 8h à 19h les jours ouvrables."
    score_exact = compute_cross_score(query, frag_exact, "Horaires et Bruits")

    # Fragment peu pertinent sans phrase exacte
    frag_loose = "La réunion annuelle de gestion financière a eu lieu en mars."
    score_loose = compute_cross_score(query, frag_loose, "Comptabilité")

    assert score_exact > 0.60
    assert score_loose < 0.20
    assert score_exact > score_loose


@pytest.mark.asyncio
async def test_rerank_candidates_reorders_by_relevance():
    query = "panne ascenseur et contrat de maintenance"

    # Candidat A : RRF initialement modéré (0.015), mais très pertinent sur l'ascenseur
    c1 = create_candidate(
        title="Contrat Ascenseur OTIS",
        content="En cas de panne ascenseur, le contrat de maintenance prévoit une intervention sous 2 heures.",
        score=0.015,
        section="Assistance et Panne",
    )

    # Candidat B : RRF initialement plus haut (0.025), mais parle seulement d'ascenseur sans parler de contrat ni maintenance
    c2 = create_candidate(
        title="Règlement Général",
        content="L'ascenseur dessert tous les étages du rez-de-chaussée au 5ème.",
        score=0.025,
        section="Parties Communes",
    )

    # Candidat C : RRF moyen (0.020), hors sujet
    c3 = create_candidate(
        title="Jardinage",
        content="La tonte des pelouses est confiée à la société Vert.",
        score=0.020,
        section="Espaces Verts",
    )

    candidates = [c2, c3, c1]
    reranked = await rerank_candidates(query=query, candidates=candidates, top_k=2)

    assert len(reranked) == 2
    # c1 doit être remonté en tête (#1) grâce à la correspondance parfaite des termes et de l'expression
    assert reranked[0].document_title == "Contrat Ascenseur OTIS"
    assert reranked[0].score > reranked[1].score
