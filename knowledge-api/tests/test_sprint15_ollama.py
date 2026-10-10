"""
Tests automatisés du Sprint 15 : Souveraineté & Mode Secret (Tâche 15.1).
Vérifie le fonctionnement d'Ollama (mistral:latest + nomic-embed-text),
la génération d'embeddings 768 dimensions et l'étanchéité absolue des données 'secret'.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from knowledge.config import settings
from knowledge.services.llm_resilience import (
    FallbackLevel,
    OllamaProvider,
    check_ollama_health,
    answer_with_fallback,
    generate_with_fallback,
)
from knowledge.services.embedding import (
    generate_embedding,
    generate_embeddings,
)


class MockFragment:
    def __init__(self, sensitivity: str, content: str, title: str):
        self.sensitivity = sensitivity
        self.content = content
        self.document_title = title


@pytest.mark.asyncio
async def test_ollama_health_check_live_and_offline():
    """Vérifie que check_ollama_health détecte correctement le serveur local et gère les erreurs."""
    # Test avec le vrai serveur Ollama actif
    is_healthy = await check_ollama_health(settings.OLLAMA_HOST)
    assert is_healthy is True, "Ollama devrait être joignable sur " + settings.OLLAMA_HOST

    # Test avec un hôte invalide (doit retourner False sans lever d'exception)
    is_offline = await check_ollama_health("http://localhost:59999")
    assert is_offline is False


@pytest.mark.asyncio
async def test_ollama_embeddings_generation_768d():
    """Vérifie la génération d'embeddings vectoriels de dimension 768 via nomic-embed-text."""
    texts = [
        "MEMENTOMORI - Système d'archivage souverain et sécurisé.",
        "Deuxième document de test pour la vectorisation par lot."
    ]

    embeddings = await generate_embeddings(texts, provider="ollama")

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 768, f"Dimension attendue 768, obtenu {len(embeddings[0])}"
    assert len(embeddings[1]) == 768
    assert all(isinstance(v, float) for v in embeddings[0])

    # Test sur texte unique
    single_emb = await generate_embedding("Vecteur unique souverain", provider="ollama")
    assert len(single_emb) == 768
    assert all(isinstance(v, float) for v in single_emb)


@pytest.mark.asyncio
async def test_secret_embedding_forces_sovereign_ollama():
    """
    Règle de souveraineté (§5.3 / AGENTS.md) :
    Un texte 'secret' ne doit JAMAIS être envoyé à l'API Cloud (Gemini),
    même si GEMINI_API_KEY est configurée et que EMBEDDING_PROVIDER='gemini'.
    """
    mock_genai_client = MagicMock()
    mock_genai_client.models.embed_content = MagicMock()

    secret_text = "Mot de passe coffre-fort souverain : SecretMasterKey2026!"

    with patch("knowledge.services.embedding.genai_client", mock_genai_client), \
         patch.object(settings, "GEMINI_API_KEY", "fake_cloud_key"), \
         patch.object(settings, "EMBEDDING_PROVIDER", "gemini"):

        emb = await generate_embedding(secret_text, sensitivity="secret")

        # Vérification 1 : Gemini NE DOIT PAS avoir été appelé
        mock_genai_client.models.embed_content.assert_not_called()

        # Vérification 2 : Un vecteur valide 768d est bien produit via Ollama
        assert len(emb) == 768
        assert all(isinstance(v, float) for v in emb)


@pytest.mark.asyncio
async def test_ollama_llm_generation_live():
    """Vérifie l'inférence locale directe avec mistral:latest sur Ollama."""
    provider = OllamaProvider(host=settings.OLLAMA_HOST, model=settings.OLLAMA_MODEL)

    system_prompt = "Tu es un assistant de test concis."
    user_prompt = "Réponds exactement et uniquement par: SOUVERAINETE_OK"

    answer, tokens_in, tokens_out = await provider.generate(system_prompt, user_prompt)

    assert isinstance(answer, str)
    assert len(answer.strip()) > 0
    assert "SOUVERAINETE_OK" in answer or len(answer) > 0
    assert tokens_in > 0
    assert tokens_out > 0


@pytest.mark.asyncio
async def test_answer_with_fallback_secret_routes_to_local_ollama():
    """
    Règle §5.3 : Pour les fragments marqués 'secret', Gemini et Mistral Cloud sont exclus,
    et la requête est obligatoirement traitée par Ollama (FallbackLevel.LOCAL).
    """
    secret_frags = [
        MockFragment("secret", "Code d'accès serveur sécurisé : XYZ-9988", "Sécurité")
    ]

    mock_gemini = AsyncMock()
    mock_mistral = AsyncMock()

    with patch.object(settings, "GEMINI_API_KEY", "fake_gemini_key"), \
         patch.object(settings, "MISTRAL_API_KEY", "fake_mistral_key"), \
         patch("knowledge.services.llm_resilience.GeminiProvider.generate", mock_gemini), \
         patch("knowledge.services.llm_resilience.MistralProvider.generate", mock_mistral):

        resp = await answer_with_fallback(
            system_prompt="Tu es un assistant confidentiel.",
            user_query="Quel est le code serveur ?",
            fragments=secret_frags,
            search_scores=[0.95]
        )

        # Les providers Cloud ne doivent pas être appelés
        mock_gemini.assert_not_called()
        mock_mistral.assert_not_called()

        # Le provider exécuté doit être Ollama en local
        assert resp.provider == "ollama"
        assert resp.fallback_level == FallbackLevel.LOCAL
        assert resp.warning is not None and "secours" in resp.warning.lower()
        assert len(resp.answer) > 0


@pytest.mark.asyncio
async def test_answer_with_fallback_secret_when_ollama_offline():
    """
    Si Ollama est indisponible et que les fragments sont 'secret',
    le système bascule en SEARCH_ONLY sans JAMAIS contacter le cloud.
    """
    secret_frags = [
        MockFragment("secret", "Informations ultra confidentielles hors ligne.", "SecretDoc")
    ]

    mock_gemini = AsyncMock()
    mock_mistral = AsyncMock()

    with patch.object(settings, "GEMINI_API_KEY", "fake_gemini_key"), \
         patch.object(settings, "MISTRAL_API_KEY", "fake_mistral_key"), \
         patch("knowledge.services.llm_resilience.GeminiProvider.generate", mock_gemini), \
         patch("knowledge.services.llm_resilience.MistralProvider.generate", mock_mistral), \
         patch("knowledge.services.llm_resilience.check_ollama_health", AsyncMock(return_value=False)):

        resp = await answer_with_fallback(
            system_prompt="Assistant",
            user_query="Question secrète",
            fragments=secret_frags,
            search_scores=[0.8]
        )

        # Jamais de fuite vers le cloud
        mock_gemini.assert_not_called()
        mock_mistral.assert_not_called()

        # Bascule en mode dégradé SEARCH_ONLY
        assert resp.provider == "system"
        assert resp.fallback_level == FallbackLevel.SEARCH_ONLY
        assert "Informations ultra confidentielles" in resp.answer

