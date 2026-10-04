"""Service de génération de réponse avec citations (§16.5, Task 3.13)."""

import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.models import LlmUsage
from knowledge.services.llm_resilience import (
    answer_with_fallback,
    LLMResponse,
)
from knowledge.services.search import SearchResult

logger = get_logger(__name__)

# Chargement du template de prompt
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
ANSWER_PROMPT_PATH = PROMPTS_DIR / "answer.txt"

def load_answer_prompt_template() -> str:
    if ANSWER_PROMPT_PATH.exists():
        return ANSWER_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Tu es un assistant de connaissance. Réponds à la question uniquement "
        "en utilisant les documents de référence ci-dessous.\n\n"
        "Documents de référence :\n---\n{chunks}\n---\n"
    )

async def generate_grounded_answer(
    question: str,
    fragments: List[SearchResult],
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Génère une réponse étayée (grounded) avec citations strictes,
    enregistre l'usage LLM et gère les limites de confidentialité.
    """
    # 1. Mise en forme des chunks pour le prompt
    chunks_text_blocks = []
    sources: List[dict[str, Any]] = []

    for rank, frag in enumerate(fragments, start=1):
        # Gestion des documents confidentiels (§16.5)
        title_for_llm = frag.document_title
        if frag.sensitivity in ("confidentiel", "secret"):
            title_for_llm = f"Document interne confidentiel #{rank}"

        chunk_repr = (
            f"[Source: {title_for_llm} | Page: {frag.page_number or 'N/A'}]\n"
            f"{frag.content}"
        )
        chunks_text_blocks.append(chunk_repr)

        sources.append({
            "document_id": str(frag.document_id),
            "fragment_id": str(frag.fragment_id),
            "document_title": frag.document_title,
            "version": frag.version,
            "score": frag.score,
            "page_number": frag.page_number,
            "sensitivity": frag.sensitivity,
            "scope": frag.scope,
            "citation_ref": frag.citation_ref
        })

    # Si aucun fragment trouvé
    if not fragments:
        return {
            "answer": "Je n'ai pas trouvé cette information dans la base de connaissances.",
            "confidence": 0.0,
            "sources": [],
            "citations": [],
            "limits": "Aucun document pertinent accessible pour ce périmètre",
            "model": "none",
            "provider": "none",
            "warning": None
        }

    # 2. Construction du prompt système
    template = load_answer_prompt_template()
    system_prompt = template.replace("{chunks}", "\n\n".join(chunks_text_blocks))

    # 3. Appel avec fallback en cascade
    scores = [f.score for f in fragments]
    llm_resp: LLMResponse = await answer_with_fallback(
        system_prompt=system_prompt,
        user_query=question,
        fragments=fragments,
        search_scores=scores
    )

    # 4. Enregistrement de la métrique d'usage dans llm_usage (§14.10)
    try:
        # Coût approximatif Gemini Flash : ~0.075$ / 1M tokens in, 0.30$ / 1M tokens out
        cost_in = (llm_resp.tokens_input / 1_000_000.0) * 0.075
        cost_out = (llm_resp.tokens_output / 1_000_000.0) * 0.30
        total_cost = Decimal(str(round(cost_in + cost_out, 6)))

        usage = LlmUsage(
            workspace_id=workspace_id,
            principal_id=principal_id,
            request_type="answer",
            model=llm_resp.model,
            provider=llm_resp.provider,
            tokens_input=llm_resp.tokens_input,
            tokens_output=llm_resp.tokens_output,
            estimated_cost=total_cost,
            latency_ms=llm_resp.latency_ms,
            confidence=str(llm_resp.confidence)
        )
        db.add(usage)
        await db.commit()
    except Exception as e:
        logger.warning("failed_to_log_llm_usage", error=str(e))
        await db.rollback()

    # 5. Extraction des citations dans la réponse
    citations = [s["document_title"] for s in sources]

    return {
        "answer": llm_resp.answer,
        "confidence": llm_resp.confidence,
        "sources": sources,
        "citations": citations,
        "limits": None,
        "model": llm_resp.model,
        "provider": llm_resp.provider,
        "warning": llm_resp.warning
    }
