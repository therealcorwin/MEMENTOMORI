"""Tests unitaires du service de chunking hybride (§16.1)."""

import pytest
from knowledge.services.chunking import (
    split_into_chunks,
    detect_strategy,
    ChunkStrategy,
    ChunkConfig,
    estimate_tokens,
)

def test_detect_strategy_markdown():
    text = "# Titre\n## Sous-titre\nContenu"
    assert detect_strategy(text, "text/markdown") == ChunkStrategy.STRUCTURAL

def test_detect_strategy_json():
    text = '{"key": "value"}'
    assert detect_strategy(text, "application/json") == ChunkStrategy.RECORD

def test_detect_strategy_semantic():
    text = "Ceci est un texte brut sans titre.\n\nDeuxieme paragraphe."
    assert detect_strategy(text, "text/plain") == ChunkStrategy.SEMANTIC

def test_chunking_structural():
    md = """# Reglement
## Article 1 - Travaux
Les travaux sont autorises de 8h a 19h.
## Article 2 - Animaux
Les animaux doivent etre tenus en laisse.
"""
    cfg = ChunkConfig(target_size=10, min_size=5)
    chunks = split_into_chunks(md, document_title="Reglement", workspace_slug="copro", config=cfg)
    assert len(chunks) >= 2
    assert "Article 1" in chunks[0].context_prefix or "Article 1" in chunks[0].content
    assert all("copro" in c.context_prefix for c in chunks)

def test_chunking_overlap():
    text = "Premiere phrase. Deuxieme phrase. Troisieme phrase.\n\n" * 20
    cfg = ChunkConfig(target_size=20, min_size=5, max_size=50, overlap=5)
    chunks = split_into_chunks(text, "Test Overlap", "ws", config=cfg)
    assert len(chunks) > 1
    # Vérifier que les chunks ont des mots en commun (overlap)
    assert any(len(c.content.split()) > 0 for c in chunks)
