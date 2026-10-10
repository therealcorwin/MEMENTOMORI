"""Script CLI de synchronisation d'un coffre de notes Markdown / Obsidian (Sprint 13, Tâche 13.2).

Scanne une arborescence de notes Markdown, extrait le frontmatter YAML et les wikilinks,
et les synchronise vers les workspaces cibles ('formation', 'dev', etc.).

Usage :
    poetry run python scripts/sync_markdown_vault.py --vault PATH [--workspace WS]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-api"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from knowledge.config import settings
from knowledge.services.markdown_sync import sync_markdown_directory

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronisation de notes Markdown/Obsidian")
    parser.add_argument("--vault", "-v", required=True, help="Chemin du coffre ou dossier de notes Markdown")
    parser.add_argument("--workspace", "-w", default="formation", help="Workspace par défaut (défaut: formation)")
    parser.add_argument("--collection", "-c", default="notes-personnelles", help="Collection par défaut")
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    print("=" * 70)
    print("📝 SPRINT 13 — Synchronisation Coffre Markdown / Obsidian")
    print(f" Répertoire : {vault_path}")
    print(f" Workspace   : {args.workspace}")
    print(f" Collection  : {args.collection}")
    print("=" * 70)

    if not vault_path.exists() or not vault_path.is_dir():
        print(f"❌ Erreur : le répertoire '{vault_path}' n'existe pas.")
        sys.exit(1)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        result = await sync_markdown_directory(
            directory_path=str(vault_path),
            db=session,
            default_workspace=args.workspace,
            default_collection=args.collection,
        )

    await engine.dispose()

    print("\n📊 Bilan de synchronisation :")
    print(f" - Notes scannées  : {result.scanned_notes}")
    print(f" - Notes ingérées  : {result.ingested_count}")
    print(f" - Ignorées (doublon): {result.skipped_count}")
    if result.errors:
        print(f" - Erreurs ({len(result.errors)}) :")
        for err in result.errors:
            print(f"   [!] {err}")
    print("\n✅ Synchronisation terminée avec succès.")


if __name__ == "__main__":
    asyncio.run(main())
