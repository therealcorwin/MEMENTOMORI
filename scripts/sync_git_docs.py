"""Script CLI de synchronisation de la documentation Git (Sprint 13, Tâche 13.1).

Scanne les dépôts Git cibles et ingère les fichiers Markdown (README, docs, architecture)
dans le workspace 'dev' (collection 'documentation-technique').

Usage :
    poetry run python scripts/sync_git_docs.py [--repo PATH] [--name NAME] [--branch BRANCH]
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
from knowledge.services.git_ingest import ingest_git_repository

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronisation de documentation Git vers le workspace dev")
    parser.add_argument("--repo", "-r", default=str(Path(__file__).parent.parent), help="Chemin du dépôt Git")
    parser.add_argument("--name", "-n", default="MEMENTOMORI", help="Nom logique du dépôt")
    parser.add_argument("--branch", "-b", default=None, help="Branche ciblée")
    parser.add_argument("--workspace", "-w", default="dev", help="Workspace cible (défaut: dev)")
    parser.add_argument("--collection", "-c", default="documentation-technique", help="Collection cible")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    print("=" * 70)
    print("🚀 SPRINT 13 — Synchronisation Documentation Git")
    print(f" Dépôt     : {repo_path}")
    print(f" Nom       : {args.name}")
    print(f" Workspace : {args.workspace}")
    print(f" Collection: {args.collection}")
    print("=" * 70)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        result = await ingest_git_repository(
            repo_path=str(repo_path),
            db=session,
            repo_name=args.name,
            branch=args.branch,
            workspace_slug=args.workspace,
            collection_name=args.collection,
        )

    await engine.dispose()

    print("\n📊 Bilan de synchronisation :")
    print(f" - Fichiers scannés : {result.scanned_files}")
    print(f" - Fichiers ingérés : {result.ingested_count}")
    print(f" - Ignorés (doublon): {result.skipped_count}")
    if result.errors:
        print(f" - Erreurs ({len(result.errors)}) :")
        for err in result.errors:
            print(f"   [!] {err}")
    print("\n✅ Synchronisation terminée avec succès.")


if __name__ == "__main__":
    asyncio.run(main())
