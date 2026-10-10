"""Service de résilience LLM avec fallback en cascade selon §16.3 (Task 3.10)."""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional
import httpx

from knowledge.config import settings
from knowledge.logging import get_logger

logger = get_logger(__name__)

class FallbackLevel(str, Enum):
    PRIMARY = "primary"         # Gemini Flash
    SECONDARY = "secondary"     # Mistral
    LOCAL = "local"             # Ollama
    SEARCH_ONLY = "search_only" # Pas de LLM, fragments bruts

@dataclass
class LLMResponse:
    answer: str
    provider: str
    model: str
    fallback_level: FallbackLevel
    latency_ms: int
    confidence: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    warning: Optional[str] = None


def compute_confidence(search_scores: List[float], fragment_count: int) -> float:
    """Calcule un score de confiance normalisé (0.0 - 1.0) basé sur la qualité du retrieval."""
    if not search_scores:
        return 0.0
    avg_score = sum(search_scores) / len(search_scores)
    coverage = min(fragment_count / 3.0, 1.0)
    spread = 1.0 - (max(search_scores) - min(search_scores)) if len(search_scores) > 1 else 1.0
    score = (avg_score * 0.5) + (coverage * 0.3) + (spread * 0.2)
    return round(max(0.0, min(1.0, score)), 2)


class BaseLLMProvider:
    provider_type: str = "cloud" # "cloud" ou "local"
    name: str = "base"
    model: str = "default"

    async def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
        """Retourne (texte_reponse, tokens_in, tokens_out)."""
        raise NotImplementedError


class GeminiProvider(BaseLLMProvider):
    provider_type = "cloud"
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY non fournie")
        
        from google import genai
        client = genai.Client(api_key=self.api_key)
        full_content = f"{system_prompt}\n\nQuestion de l'utilisateur :\n{user_prompt}"
        
        # Exécution dans un threadpool pour l'appel synchrone
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=self.model,
                contents=full_content
            )
        )
        answer = response.text or ""
        tokens_in = len(full_content.split())
        tokens_out = len(answer.split())
        return answer, tokens_in, tokens_out


class MistralProvider(BaseLLMProvider):
    provider_type = "cloud"
    name = "mistral"

    def __init__(self, api_key: str, model: str = "mistral-small-latest"):
        self.api_key = api_key
        self.model = model

    async def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY non fournie")

        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            tokens_in = data.get("usage", {}).get("prompt_tokens", 0)
            tokens_out = data.get("usage", {}).get("completion_tokens", 0)
            return answer, tokens_in, tokens_out


class OllamaProvider(BaseLLMProvider):
    provider_type = "local"
    name = "ollama"

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = (host or settings.OLLAMA_HOST).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    async def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "num_predict": 256,
                "temperature": 0.2
            }
        }
        # Timeout adapté pour l'inférence locale CPU / premier chargement de modèle 12B (120s)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("response", "")
            return answer, data.get("prompt_eval_count", 0), data.get("eval_count", 0)


_ollama_cache: dict[str, tuple[bool, float]] = {}

async def check_ollama_health(host: Optional[str] = None, force_refresh: bool = False) -> bool:
    """Vérifie rapidement si Ollama est actif en local avec mise en cache du statut par hôte (30s)."""
    target_host = (host or settings.OLLAMA_HOST).rstrip("/")
    now = time.time()
    if not force_refresh and target_host in _ollama_cache:
        cached_status, last_checked = _ollama_cache[target_host]
        if (now - last_checked) < 30.0:
            return cached_status

    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{target_host}/api/tags")
            status = (resp.status_code == 200)
    except Exception:
        status = False

    _ollama_cache[target_host] = (status, now)
    return status


async def answer_with_fallback(
    system_prompt: str,
    user_query: str,
    fragments: List[Any],
    search_scores: List[float],
    timeout: float = 10.0,
    max_retries: int = 1,
) -> LLMResponse:
    """Tente chaque provider en cascade avec retry selon §16.3."""
    start_time = time.time()
    conf = compute_confidence(search_scores, len(fragments))

    # 1. Vérification de sensibilité (§5.3 & Directive Souveraineté) :
    # - 'secret' : Aucun Cloud (ni Gemini ni Mistral Cloud) -> Ollama local uniquement
    # - 'interne' ou 'confidentiel' : Gemini INTERDIT -> Mistral (Cloud) en primaire ou Ollama local
    # - 'public' uniquement : Gemini Cloud autorisé en primaire, puis Mistral, puis Ollama local
    has_secret_fragments = any(getattr(f, "sensitivity", "interne") == "secret" for f in fragments)
    has_non_public_fragments = any(getattr(f, "sensitivity", "interne") != "public" for f in fragments)

    providers: List[tuple[BaseLLMProvider, FallbackLevel]] = []

    if has_secret_fragments:
        logger.warning("secret_fragments_detected_bypassing_cloud_llms")
    elif has_non_public_fragments:
        logger.info("non_public_fragments_detected_bypassing_gemini")
        if settings.MISTRAL_API_KEY:
            providers.append((MistralProvider(settings.MISTRAL_API_KEY), FallbackLevel.PRIMARY))
    else:
        # Fragments 100% publics (ou aucun fragment fourni)
        if settings.GEMINI_API_KEY:
            providers.append((GeminiProvider(settings.GEMINI_API_KEY, settings.LLM_MODEL), FallbackLevel.PRIMARY))
        if settings.MISTRAL_API_KEY:
            providers.append((MistralProvider(settings.MISTRAL_API_KEY), FallbackLevel.SECONDARY))

    # Provider local Ollama si disponible (secours ou traitement souverain)
    if await check_ollama_health():
        providers.append((OllamaProvider(), FallbackLevel.LOCAL))

    # Si le contexte documentaire n'a pas encore été injecté dans user_query, on l'ajoute pour le LLM
    augmented_user_query = user_query
    if fragments and not any(getattr(f, "content", "") in user_query for f in fragments if getattr(f, "content", "")):
        context_str = "\n\n".join([
            f"[{getattr(f, 'document_title', 'Document')}] :\n{getattr(f, 'content', str(f))}"
            for f in fragments
        ])
        augmented_user_query = f"Contexte documentaire fourni :\n{context_str}\n\nQuestion :\n{user_query}\n\nRéponds précisément à la question en t'appuyant strictement sur le contexte documentaire ci-dessus."

    for provider, level in providers:
        for attempt in range(1 + max_retries):
            try:
                t0 = time.time()
                logger.info("attempting_llm_generation", provider=provider.name, attempt=attempt+1, level=level.value)
                current_timeout = max(timeout, 120.0) if level == FallbackLevel.LOCAL else timeout
                answer, tokens_in, tokens_out = await asyncio.wait_for(
                    provider.generate(system_prompt, augmented_user_query),
                    timeout=current_timeout
                )
                latency = int((time.time() - t0) * 1000)
                warning = None
                if level != FallbackLevel.PRIMARY:
                    warning = f"Réponse générée via provider de secours ({provider.name})"

                return LLMResponse(
                    answer=answer.strip(),
                    provider=provider.name,
                    model=provider.model,
                    fallback_level=level,
                    latency_ms=latency,
                    confidence=conf,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                    warning=warning
                )
            except Exception as e:
                logger.warning(
                    "llm_provider_attempt_failed",
                    provider=provider.name,
                    attempt=attempt+1,
                    error=str(e)
                )
                if attempt < max_retries:
                    await asyncio.sleep(1.0)

    # Mode dégradé SEARCH_ONLY si aucun LLM n'a répondu
    latency = int((time.time() - start_time) * 1000)
    logger.info("all_llm_providers_failed_fallback_to_search_only")

    # Synthèse directe des extraits
    extraits = []
    for f in fragments[:5]:
        title = getattr(f, "document_title", "Document")
        content = getattr(f, "content", str(f)).strip()
        if len(content) > 1500:
            content = content[:1500] + "..."
        extraits.append(f"- [{title}] :\n{content}")

    degraded_answer = (
        "Le service de génération automatique est momentanément indisponible.\n\n"
        "Voici les extraits les plus pertinents identifiés dans votre base de connaissances :\n\n"
        + "\n\n".join(extraits)
    )

    return LLMResponse(
        answer=degraded_answer,
        provider="system",
        model="search_only",
        fallback_level=FallbackLevel.SEARCH_ONLY,
        latency_ms=latency,
        confidence=conf,
        tokens_input=0,
        tokens_output=0,
        warning="Synthèse IA indisponible — extraits bruts retournés"
    )


async def generate_with_fallback(
    prompt: str,
    system_prompt: str = "Tu es un assistant précis et concis.",
    temperature: float = 0.0,
    max_tokens: int = 256,
    timeout: float = 8.0,
    sensitivity: str = "public",
) -> tuple[str, FallbackLevel, str]:
    """Génération simple de texte avec cascade de résilience selon la sensibilité."""
    providers: list[tuple[BaseLLMProvider, FallbackLevel]] = []

    if sensitivity == "secret":
        logger.warning("secret_sensitivity_bypassing_cloud_llms")
    elif sensitivity != "public":
        # Interne ou confidentiel : Gemini exclu, Mistral en primaire
        logger.info("non_public_sensitivity_bypassing_gemini")
        if settings.MISTRAL_API_KEY:
            providers.append((MistralProvider(settings.MISTRAL_API_KEY), FallbackLevel.PRIMARY))
    else:
        # Public : Gemini autorisé en primaire
        if settings.GEMINI_API_KEY:
            providers.append((GeminiProvider(settings.GEMINI_API_KEY, settings.LLM_MODEL), FallbackLevel.PRIMARY))
        if settings.MISTRAL_API_KEY:
            providers.append((MistralProvider(settings.MISTRAL_API_KEY), FallbackLevel.SECONDARY))

    if await check_ollama_health():
        providers.append((OllamaProvider(), FallbackLevel.LOCAL))

    for provider, level in providers:
        try:
            current_timeout = max(timeout, 120.0) if level == FallbackLevel.LOCAL else timeout
            answer, tokens_in, tokens_out = await asyncio.wait_for(
                provider.generate(system_prompt=system_prompt, user_prompt=prompt),
                timeout=current_timeout
            )
            return answer.strip(), level, provider.model
        except Exception as e:
            logger.warning("generate_fallback_failed", provider=provider.name, error=str(e))

    raise RuntimeError("Tous les providers LLM ont échoué pour la génération de texte.")
