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
    task_type: Optional[str] = None
) -> List[float]:
    """Génère un vecteur d'embedding de 768 dimensions pour un texte unique."""
    embeddings = await generate_embeddings([text], model=model, task_type=task_type)
    return embeddings[0]


async def generate_embeddings(
    texts: List[str],
    model: Optional[str] = None,
    task_type: Optional[str] = None
) -> List[List[float]]:
    """Génère des embeddings vectoriels par lot (batch)."""
    if not texts:
        return []

    target_model = model or settings.EMBEDDING_MODEL

    # Utiliser le SDK Google GenAI si la clé est fournie et le client initialisé
    if genai_client and settings.GEMINI_API_KEY:
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
            logger.error("gemini_embedding_failed_fallback_to_mock", error=str(e))
            # Fallback en mode résilience
            return [_generate_mock_embedding(t) for t in texts]

    # Mode fallback déterministe (hors ligne / développement sans clé)
    logger.debug("generating_mock_embeddings", count=len(texts))
    return [_generate_mock_embedding(t) for t in texts]
