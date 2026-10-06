"""Tests de validation du service de Grounding Verification post-LLM (§17 B11)."""

import pytest
import uuid
from knowledge.services.search import SearchResult
from knowledge.services.grounding import verify_grounding, extract_factual_entities


def create_dummy_fragment(title: str, content: str, page: int = 1) -> SearchResult:
    return SearchResult(
        fragment_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        version=1,
        content=content,
        context_prefix=f"[Document: {title} | Page {page}]",
        page_number=page,
        score=0.85,
        citation_ref={"title": title, "page": page},
        sensitivity="interne",
        scope="copro",
    )


def test_extract_factual_entities():
    text = (
        "Le montant s'élève à 1 250 € pour le lot 42 situé au bâtiment B. "
        "La quote-part est de 15% selon l'article 24 en date du 15/03/2024."
    )
    entities = extract_factual_entities(text)
    assert any("1 250 €" in e or "1250" in e for e in entities)
    assert any("lot 42" in e for e in entities)
    assert any("bâtiment b" in e for e in entities)
    assert any("15%" in e for e in entities)
    assert any("article 24" in e for e in entities)


def test_grounding_perfect_match():
    doc_content = (
        "Le budget prévisionnel pour les travaux d'ascenseur est de 1 250 € pour le lot 42. "
        "Application de l'article 24 voté en 2024."
    )
    fragments = [create_dummy_fragment("Budget Copro", doc_content)]

    answer = "Les travaux pour le lot 42 représentent un montant de 1 250 € selon l'article 24 voté en 2024."
    result = verify_grounding(answer, fragments, strict_threshold=0.80)

    assert result.is_grounded is True
    assert result.grounding_score >= 0.80
    assert len(result.unverified_entities) == 0
    assert result.warning is None


def test_grounding_detects_hallucination():
    doc_content = (
        "Les charges pour le lot 12 s'élèvent à 350 € par trimestre."
    )
    fragments = [create_dummy_fragment("Appel de charges", doc_content)]

    # Le LLM hallucine un montant erroné de 9 500 € et un mauvais lot (lot 99)
    hallucinated_answer = (
        "D'après vos documents, les charges s'élèvent à 9 500 € pour le lot 99."
    )
    result = verify_grounding(hallucinated_answer, fragments, strict_threshold=0.80)

    assert result.is_grounded is False
    assert result.grounding_score < 0.50
    assert len(result.unverified_entities) >= 1
    assert result.warning is not None
    assert "Vérification de fidélité documentaire (B11)" in result.warning


def test_grounding_declarative_no_entities():
    doc_content = "Le règlement interdit le stationnement des vélos dans les parties communes."
    fragments = [create_dummy_fragment("Règlement Intérieur", doc_content)]

    answer = "Il est interdit de garer son vélo dans les parties communes de l'immeuble."
    result = verify_grounding(answer, fragments)

    assert result.is_grounded is True
    assert result.grounding_score == 1.0
    assert result.total_entities == 0
    assert result.warning is None
