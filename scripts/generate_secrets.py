#!/usr/bin/env python3
"""
Générateur automatique de secrets pour MEMENTOMORI.
Génère des mots de passe et clés aléatoires cryptographiquement sûrs
et crée ou met à jour le fichier .env sans écraser les clés d'API existantes.
"""

from __future__ import annotations

import secrets
from pathlib import Path


def generate_secrets() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    env_file = root_dir / ".env"
    env_example = root_dir / ".env.example"

    if not env_example.exists():
        print("Erreur : .env.example introuvable.")
        return

    # Valeurs générées par défaut
    random_secrets = {
        "PAPERLESS_DB_PASSWORD": secrets.token_hex(32),
        "PAPERLESS_ADMIN_PASSWORD": secrets.token_urlsafe(16),
        "AUTHENTIK_DB_PASSWORD": secrets.token_hex(32),
        "AUTHENTIK_SECRET_KEY": secrets.token_hex(64),
        "KNOWLEDGE_DB_PASSWORD": secrets.token_hex(32),
        "REDIS_PASSWORD": secrets.token_hex(32),
        "GRAFANA_ADMIN_PASSWORD": secrets.token_urlsafe(16),
    }

    if env_file.exists():
        print(f"Le fichier {env_file} existe déjà. Aucune écrasement pour préserver vos secrets.")
        return

    example_lines = env_example.read_text(encoding="utf-8").splitlines()
    output_lines = []

    for line in example_lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            key, _ = trimmed.split("=", 1)
            if key in random_secrets:
                output_lines.append(f"{key}={random_secrets[key]}")
            else:
                output_lines.append(line)
        else:
            output_lines.append(line)

    env_file.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"Fichier .env créé avec succès dans {env_file}")
    print("N'oubliez pas de renseigner GEMINI_API_KEY et MISTRAL_API_KEY au besoin.")


if __name__ == "__main__":
    generate_secrets()

