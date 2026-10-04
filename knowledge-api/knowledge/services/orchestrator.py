"""
Service Orchestrateur Central Multi-Agents (Sprint 7, Tâches 7.3, 7.4, 7.5, 7.9 & §8, §16.5, §16.13).
Gère la classification des intentions, le routage vers sous-agents, la fusion cross-workspaces
et garantit qu'aucun accès direct aux données brutes n'est possible sans délégation.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.models import Workspace, Principal, Policy
from knowledge.services.llm_resilience import generate_with_fallback, answer_with_fallback
from knowledge.services.adaptive_search import adaptive_hybrid_search
from knowledge.services.search import SearchResult
from knowledge.services.generation import generate_grounded_answer

logger = get_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
CLASSIFY_MULTI_PATH = PROMPTS_DIR / "classify_multi.txt"
ANSWER_MULTI_PATH = PROMPTS_DIR / "answer_multi.txt"

# Mapping canonique des workspaces vers leurs sous-agents dédiés (§8.4)
WORKSPACE_TO_AGENT = {
    "copro-jardins": "csbot",
    "finances-perso": "agent-finances",
    "sante-perso": "agent-sante",
    "dev": "agent-dev",
}


@dataclass
class WorkspaceMatch:
    workspace_slug: str
    workspace_id: uuid.UUID
    confidence: float
    role: str  # "primary" | "secondary"
    description: str = ""


@dataclass
class ClassificationResult:
    workspaces: List[WorkspaceMatch]
    strategy: str  # "single" | "multi" | "unknown"
    question: str
    raw_llm_output: Optional[str] = None


def load_prompt(file_path: Path, default: str) -> str:
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return default


def fallback_classify_by_keywords(
    question: str,
    workspaces: List[Workspace]
) -> ClassificationResult:
    """Classifieur de secours déterministe par mots-clés et règles sémantiques."""
    q_lower = question.lower()
    scores: dict[str, float] = {}

    keyword_maps = {
        "copro-jardins": [
            "copro", "jardin", "syndic", "ascenseur", "otis", "charges", "ag",
            "vert avenir", "ravalement", "lot 12", "lot 42", "assemblée", "pv",
            "gardien", "chaudiere", "eau froide", "parties communes", "travaux",
            "bruit", "bruyant", "horaires", "règlement", "voisinage", "ordures",
            "poubelles", "parking", "bâtiment", "balcon"
        ],
        "finances-perso": [
            "banque", "compte", "solde", "impôt", "livret", "créditeur", "épargne",
            "débit", "revenus", "fiscal", "trésorerie", "moyens", "payer", "argent",
            "dépense", "virement", "budget", "patrimoine", "bourse"
        ],
        "sante-perso": [
            "santé", "médecin", "ordonnance", "sang", "analyse", "traitement",
            "médicament", "clinique", "docteur", "consultation", "vaccin"
        ],
        "dev": [
            "docker", "compose", "git", "traefik", "port", "code", "script",
            "base de données", "pgvector", "python", "fastapi", "bug", "deploy",
            "infrastructure", "stack", "serveur", "api"
        ],
    }

    ws_by_slug = {w.slug: w for w in workspaces}

    for slug, kws in keyword_maps.items():
        if slug not in ws_by_slug:
            continue
        match_count = sum(1 for kw in kws if kw in q_lower)
        if match_count > 0:
            scores[slug] = min(0.95, 0.45 + (match_count * 0.15))

    # Détection spécifique des questions transversales (ex: moyens de payer l'appel de fonds)
    is_cross_copro_finances = (
        ("appel de fonds" in q_lower or "charges" in q_lower) and
        ("moyens" in q_lower or "payer" in q_lower or "solde" in q_lower or "compte" in q_lower)
    )
    if is_cross_copro_finances and "copro-jardins" in ws_by_slug and "finances-perso" in ws_by_slug:
        scores["copro-jardins"] = max(scores.get("copro-jardins", 0.0), 0.85)
        scores["finances-perso"] = max(scores.get("finances-perso", 0.0), 0.80)

    if not scores:
        return ClassificationResult(
            workspaces=[],
            strategy="unknown",
            question=question,
            raw_llm_output="fallback_empty"
        )

    # Trier par score décroissant
    sorted_matches = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    matches: List[WorkspaceMatch] = []

    for rank, (slug, score) in enumerate(sorted_matches[:3]):
        ws = ws_by_slug[slug]
        matches.append(
            WorkspaceMatch(
                workspace_slug=slug,
                workspace_id=ws.id,
                confidence=score,
                role="primary" if rank == 0 else "secondary",
                description=str(ws.settings.get("description", ws.name))
            )
        )

    if len(matches) == 1 or (matches[0].confidence >= 0.85 and (len(matches) == 1 or matches[1].confidence < 0.40)):
        strategy = "single"
    elif len(matches) >= 2 and matches[1].confidence >= 0.40:
        strategy = "multi"
    else:
        strategy = "single"

    return ClassificationResult(
        workspaces=matches,
        strategy=strategy,
        question=question,
        raw_llm_output="fallback_keyword_matched"
    )


async def classify_question(
    question: str,
    db: AsyncSession
) -> ClassificationResult:
    """
    Classifie la question utilisateur pour identifier le ou les workspaces cibles (§16.13).
    Utilise Gemini Flash déterministe (température 0.0) avec repli automatique par mots-clés.
    """
    # 1. Chargement des workspaces actifs
    res = await db.execute(select(Workspace).order_by(Workspace.slug))
    workspaces = res.scalars().all()
    if not workspaces:
        return ClassificationResult([], "unknown", question)

    ws_by_slug = {w.slug: w for w in workspaces}

    # Description formatée des workspaces
    ws_desc_lines = []
    for w in workspaces:
        desc = w.settings.get("description") if isinstance(w.settings, dict) else w.name
        ws_desc_lines.append(f"- {w.slug} : {desc}")
    ws_desc_str = "\n".join(ws_desc_lines)

    prompt_template = load_prompt(
        CLASSIFY_MULTI_PATH,
        "Tu es un classificateur de workspaces.\n{workspaces_description}\nQuestion: {question}"
    )
    prompt = prompt_template.format(
        workspaces_description=ws_desc_str,
        question=question
    )

    try:
        raw_resp, level, model = await generate_with_fallback(
            prompt=prompt,
            temperature=0.0,
            max_tokens=64
        )
        raw_resp_str = raw_resp.strip()
    except Exception as e:
        logger.warning("orchestrator_classification_llm_failed", error=str(e))
        return fallback_classify_by_keywords(question, workspaces)

    # Parsing de la réponse du modèle
    if "UNKNOWN" in raw_resp_str.upper():
        # Tentative via fallback au cas où le LLM a été trop conservateur
        fb = fallback_classify_by_keywords(question, workspaces)
        if fb.strategy != "unknown":
            return fb
        return ClassificationResult([], "unknown", question, raw_llm_output=raw_resp_str)

    matches: List[WorkspaceMatch] = []
    lines = raw_resp_str.splitlines()

    for line in lines:
        line = line.strip()
        match = re.search(r"(PRIMARY|SECONDARY)\s*:\s*([a-zA-Z0-9_\-]+)(?:\s*\(([0-9\.]+)\))?", line, re.IGNORECASE)
        if match:
            role_tag = match.group(1).lower()
            slug = match.group(2).lower()
            conf_str = match.group(3)
            confidence = float(conf_str) if conf_str else (0.90 if role_tag == "primary" else 0.70)

            if slug in ws_by_slug and slug not in [m.workspace_slug for m in matches]:
                ws = ws_by_slug[slug]
                matches.append(
                    WorkspaceMatch(
                        workspace_slug=slug,
                        workspace_id=ws.id,
                        confidence=confidence,
                        role="primary" if role_tag == "primary" else "secondary",
                        description=str(ws.settings.get("description", ws.name))
                    )
                )

    if not matches:
        return fallback_classify_by_keywords(question, workspaces)

    # Règles de stratégie (§16.13)
    if len(matches) == 1:
        strategy = "single"
    elif matches[0].confidence >= 0.85 and matches[1].confidence < 0.40:
        strategy = "single"
        matches = [matches[0]]
    elif matches[1].confidence >= 0.40:
        strategy = "multi"
    else:
        strategy = "single"
        matches = [matches[0]]

    return ClassificationResult(
        workspaces=matches,
        strategy=strategy,
        question=question,
        raw_llm_output=raw_resp_str
    )


async def delegate_to_subagent(
    workspace_slug: str,
    query: str,
    db: AsyncSession,
    is_answer: bool = True,
    top_k: int = 5
) -> dict[str, Any]:
    """
    Délègue l'exécution à un sous-agent spécialisé (§8.2, Tâche 7.4).
    L'orchestrateur emprunte l'identité du sous-agent habilité pour accéder au workspace.
    """
    agent_name = WORKSPACE_TO_AGENT.get(workspace_slug, "csbot")

    # 1. Récupération du Workspace et de l'Agent Principal
    ws = (await db.execute(select(Workspace).where(Workspace.slug == workspace_slug))).scalar_one_or_none()
    if not ws:
        raise ValueError(f"Workspace inconnu : {workspace_slug}")

    principal = (await db.execute(select(Principal).where(Principal.external_id == agent_name))).scalar_one_or_none()
    if not principal:
        raise ValueError(f"Agent principal introuvable pour {agent_name}")

    # 2. Vérification des Politiques de l'agent
    policy = (await db.execute(
        select(Policy).where(
            Policy.workspace_id == ws.id,
            Policy.principal_id == principal.id
        )
    )).scalar_one_or_none()

    if not policy:
        logger.error("subagent_unauthorized_on_workspace", agent=agent_name, workspace=workspace_slug)
        raise PermissionError(f"L'agent {agent_name} n'a aucune politique sur le workspace {workspace_slug}")

    allowed_scopes = policy.allowed_scopes or ["public"]
    max_sensitivity = policy.max_sensitivity or "interne"

    # 3. Recherche adaptative
    results, final_query, quality = await adaptive_hybrid_search(
        query=query,
        workspace_ids=[ws.id],
        allowed_scopes=allowed_scopes,
        max_sensitivity=max_sensitivity,
        db=db,
        top_k=top_k
    )

    if not is_answer:
        return {
            "status": "success",
            "workspace_slug": workspace_slug,
            "agent": agent_name,
            "query": final_query,
            "confidence": quality.confidence,
            "results_count": len(results),
            "results": [
                {
                    "fragment_id": str(r.fragment_id),
                    "document_title": r.document_title,
                    "score": r.score,
                    "content": r.content,
                    "scope": r.scope,
                    "sensitivity": r.sensitivity
                }
                for r in results
            ]
        }

    # 4. Génération de réponse via l'agent
    answer_dict = await generate_grounded_answer(
        question=final_query,
        fragments=results,
        workspace_id=ws.id,
        principal_id=principal.id,
        db=db
    )

    return {
        "status": "success",
        "workspace_slug": workspace_slug,
        "agent": agent_name,
        "query": final_query,
        "confidence": answer_dict.get("confidence", "low"),
        "answer": answer_dict.get("answer", ""),
        "sources": answer_dict.get("sources", []),
        "results_count": len(results),
        "results": results
    }


async def multi_workspace_search(
    question: str,
    classification: ClassificationResult,
    db: AsyncSession,
    top_total: int = 7
) -> dict[str, Any]:
    """
    Recherche parallèle dans plusieurs workspaces et synthèse transversale (§16.13, Tâche 7.9).
    """
    target_workspaces = classification.workspaces[:3]
    logger.info(
        "multi_workspace_search_started",
        question=question[:50],
        workspaces=[m.workspace_slug for m in target_workspaces]
    )

    # 1. Recherches parallèles déléguées aux sous-agents respectifs
    tasks = [
        delegate_to_subagent(
            workspace_slug=m.workspace_slug,
            query=question,
            db=db,
            is_answer=False,
            top_k=5
        )
        for m in target_workspaces
    ]
    subagent_responses = await asyncio.gather(*tasks, return_exceptions=True)

    all_fragments: List[dict[str, Any]] = []
    sources: List[dict[str, Any]] = []

    for m, resp in zip(target_workspaces, subagent_responses):
        if isinstance(resp, Exception) or not isinstance(resp, dict):
            logger.warning("subagent_search_error", workspace=m.workspace_slug, error=str(resp))
            continue

        for r in resp.get("results", []):
            r["source_workspace"] = m.workspace_slug
            all_fragments.append(r)
            sources.append({
                "document_title": r["document_title"],
                "workspace": m.workspace_slug,
                "score": r["score"],
                "sensitivity": r["sensitivity"]
            })

    # 2. Tri par score global et rétention du top_total (7 fragments max)
    all_fragments.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    top_fragments = all_fragments[:top_total]

    if not top_fragments:
        return {
            "strategy": "multi",
            "workspaces": [m.workspace_slug for m in target_workspaces],
            "answer": "Je n'ai pas trouvé d'informations suffisantes dans les différents espaces interrogés pour répondre à votre question transversale.",
            "confidence": "none",
            "sources": []
        }

    # 3. Formatage pour le prompt de synthèse multi-workspaces
    chunks_text_blocks = []
    for rank, frag in enumerate(top_fragments, start=1):
        ws_slug = frag.get("source_workspace", "inconnu")
        title = frag.get("document_title", "Document")
        if frag.get("sensitivity") in ("confidentiel", "secret"):
            title = f"Document interne ({ws_slug})"

        block = (
            f"[WORKSPACE:{ws_slug} | Source: {title}]\n"
            f"{frag.get('content', '')}"
        )
        chunks_text_blocks.append(block)

    prompt_template = load_prompt(
        ANSWER_MULTI_PATH,
        "Tu es un assistant de synthèse multi-workspaces.\n\nExtraits :\n{chunks}\n\nQuestion : {question}"
    )
    prompt = prompt_template.format(
        chunks="\n\n---\n\n".join(chunks_text_blocks),
        question=question
    )

    # 4. Appel LLM de synthèse avec fallback
    search_scores = [float(f.get("score", 0.0)) for f in top_fragments]
    llm_resp = await answer_with_fallback(
        system_prompt=prompt,
        user_query=question,
        fragments=top_fragments,
        search_scores=search_scores,
    )

    return {
        "strategy": "multi",
        "workspaces": [m.workspace_slug for m in target_workspaces],
        "question": question,
        "answer": llm_resp.answer,
        "confidence": llm_resp.confidence,
        "model": llm_resp.model,
        "sources": sources,
        "fragments_used_count": len(top_fragments)
    }


async def orchestrate_query(
    question: str,
    db: AsyncSession,
    requesting_principal: Optional[Principal] = None
) -> dict[str, Any]:
    """
    Point d'entrée universel de l'Orchestrateur Multi-Agents (§8.1).
    Classifie la question, route vers le(s) sous-agent(s) et retourne la réponse consolidée.
    """
    logger.info("orchestrator_query_received", question=question[:60])

    # 1. Classification
    classification = await classify_question(question=question, db=db)
    logger.info(
        "orchestrator_classified",
        strategy=classification.strategy,
        workspaces=[f"{m.workspace_slug} ({m.confidence:.2f})" for m in classification.workspaces]
    )

    # 2. Routage selon stratégie
    if classification.strategy == "unknown" or not classification.workspaces:
        return {
            "strategy": "unknown",
            "answer": (
                "Je n'ai pas trouvé d'espace de connaissances correspondant à votre demande. "
                "Les espaces disponibles actuellement concernent la copropriété, les finances personnelles, la santé et le développement."
            ),
            "confidence": "none",
            "sources": [],
            "workspaces": []
        }

    if classification.strategy == "single":
        primary = classification.workspaces[0]
        delegated = await delegate_to_subagent(
            workspace_slug=primary.workspace_slug,
            query=question,
            db=db,
            is_answer=True
        )
        return {
            "strategy": "single",
            "workspace": primary.workspace_slug,
            "agent": delegated.get("agent"),
            "answer": delegated.get("answer"),
            "confidence": delegated.get("confidence"),
            "sources": delegated.get("sources", []),
            "results_count": delegated.get("results_count", 0)
        }

    # Stratégie multi-workspaces (§16.13)
    return await multi_workspace_search(
        question=question,
        classification=classification,
        db=db
    )
