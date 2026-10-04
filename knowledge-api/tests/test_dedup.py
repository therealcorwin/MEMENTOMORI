"""Tests unitaires du service de déduplication SHA-256 (§16.4)."""

import pytest
from knowledge.services.dedup import compute_content_hash, normalize_text

def test_compute_content_hash_identical():
    text1 = "Contenu avec   espaces multiples et Retour Ligne.\n"
    text2 = "contenu avec espaces multiples et retour ligne."
    assert compute_content_hash(text1) == compute_content_hash(text2)

def test_compute_content_hash_different():
    text1 = "Contenu version 1"
    text2 = "Contenu version 2"
    assert compute_content_hash(text1) != compute_content_hash(text2)
