"""
Router de l'orchestrateur central multi-agents POST /v1/orchestrate (Sprint 7, Tâches 7.3, 7.4, 7.9).
Fournit les points d'entrée de classification automatique et d'interrogation cross-workspaces.
"""

from __future__ import annotations

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.dependencies import get_db, get_current_principal
from knowledge.logging import get_logger
from knowledge.models import Principal
from knowledge.services.orchestrator import (
    classify_question,
    orchestrate_query,
    delegate_to_subagent,
    ClassificationResult
)

logger = get_logger(__name__)
router = APIRouter(prefix="/v1/orchestrate", tags=["Orchestrator"])


class ClassifyRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)


class OrchestrateQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    top_k: int = Field(5, ge=1, le=20)


@router.post("/classify")
async def classify_route(
    req: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Classifie la question utilisateur parmi les workspaces actifs (§16.13)."""
    logger.info("orchestrator_classify_api", query=req.query[:60], principal=principal.external_id)
    res = await classify_question(question=req.query, db=db)
    return {
        "query": req.query,
        "strategy": res.strategy,
        "workspaces": [
            {
                "slug": m.workspace_slug,
                "confidence": m.confidence,
                "role": m.role,
                "description": m.description
            }
            for m in res.workspaces
        ],
        "raw_output": res.raw_llm_output
    }


@router.post("/query")
async def orchestrate_query_route(
    req: OrchestrateQueryRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Point d'entrée universel : classification, routage automatique et réponse (§8.1, §16.13)."""
    logger.info("orchestrator_query_api", query=req.query[:60], principal=principal.external_id)
    return await orchestrate_query(
        question=req.query,
        db=db,
        requesting_principal=principal
    )
