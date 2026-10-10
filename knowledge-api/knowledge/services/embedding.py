"""Service de calcul d'embeddings vectoriels (Gemini text-embedding-004, Task 3.5)."""

import hashlib
import math
from typing import List, Optional
from knowledge.config import settings
from knowledge.logging import get_logger

logger = get_logger(__name__)

# Initialisation du client google-genai si clé présente
genai_client = None
if settings.GEMINI_API_KEY:
    try:
        from google import genai
        genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        logger.warning("gemini_client_init_failed", error=str(e))


import httpx


async def _generate_ollama_embeddings(
    texts: List[str],
    model: Optional[str] = None
) -> Optional[List[List[float]]]:
    """Génère les embeddings via l'API locale d'Ollama (/api/embed)."""
    host = settings.OLLAMA_HOST.rstrip("/")
    url = f"{host}/api/embed"
    target_model = model or settings.OLLAMA_EMBEDDING_MODEL
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={"model": target_model, "input": texts})
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if len(embeddings) == len(texts):
                    return embeddings
    except Exception as e:
        logger.warning("ollama_embeddings_failed", error=str(e))
    return None


def _generate_mock_embedding(text: str, dim: int = 768) -> List[float]:
    """Génère un embedding déterministe normalisé basé sur SHA-256 (mode offline/fallback/tests)."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Répéter les octets pour couvrir 'dim' valeurs
    raw_vals = [float((h[i % len(h)] ^ (i & 0xFF)) - 128) for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in raw_vals)) or 1.0
    return [v / norm for v in raw_vals]


async def generate_embedding(
    text: str,
    model: Optional[str] = None,
    task_type: Optional[str] = None,
    provider: Optional[str] = None,
    sensitivity: Optional[str] = None,
) -> List[float]:
    """Génère un vecteur d'embedding de 768 dimensions pour un texte unique."""
    embeddings = await generate_embeddings(
        [text],
        model=model,
        task_type=task_type,
        provider=provider,
        sensitivity=sensitivity,
    )
    return embeddings[0]


async def generate_embeddings(
    texts: List[str],
    model: Optional[str] = None,
    task_type: Optional[str] = None,
    provider: Optional[str] = None,
    sensitivity: Optional[str] = None,
) -> List[List[float]]:
    """Génère des embeddings vectoriels par lot (batch)."""
    if not texts:
        return []

    active_provider = provider or settings.EMBEDDING_PROVIDER
    is_secret = (sensitivity == "secret")

    # Règle de souveraineté absolue §5.3 : Aucun contenu secret ne part vers les API Cloud
    if is_secret:
        active_provider = "ollama"

    # 1. Utilisation prioritaire d'Ollama si configuré explicitement ou si secret
    if active_provider == "ollama":
        ollama_embs = await _generate_ollama_embeddings(texts, model=model or settings.OLLAMA_EMBEDDING_MODEL)
        if ollama_embs:
            logger.info("generating_embeddings_via_ollama", count=len(texts), model=settings.OLLAMA_EMBEDDING_MODEL, is_secret=is_secret)
            return ollama_embs
        if is_secret:
            # En mode secret, si Ollama est indisponible, fallback local déterministe (JAMAIS Gemini)
            logger.warning("ollama_unavailable_for_secret_fallback_to_mock")
            return [_generate_mock_embedding(t) for t in texts]

    target_model = model or settings.EMBEDDING_MODEL

    # 2. Utiliser le SDK Google GenAI si configuré et clé fournie (uniquement si non-secret)
    if genai_client and settings.GEMINI_API_KEY and active_provider == "gemini" and not is_secret:
        try:
            logger.info("generating_embeddings_via_gemini", count=len(texts), model=target_model)
            response = genai_client.models.embed_content(
                model=target_model,
                contents=texts,
            )
            # Extraire les listes de floats
            embeddings: List[List[float]] = []
            for item in response.embeddings:
                embeddings.append(item.values)
            return embeddings
        except Exception as e:
            logger.error("gemini_embedding_failed_attempting_ollama_fallback", error=str(e))

    # 3. Secours local Ollama si Gemini échoue ou n'est pas disponible
    ollama_embs = await _generate_ollama_embeddings(texts, model=settings.OLLAMA_EMBEDDING_MODEL)
    if ollama_embs:
        logger.info("generating_embeddings_via_ollama_fallback", count=len(texts))
        return ollama_embs

    # 4. Mode fallback déterministe (hors ligne / tests isolés)
    logger.debug("generating_mock_embeddings", count=len(texts))
    return [_generate_mock_embedding(t) for t in texts]
