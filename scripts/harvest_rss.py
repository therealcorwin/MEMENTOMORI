"""Script CLI de moissonnage de flux RSS & Veille (Sprint 13, Tâche 13.3).

Collecte les flux RSS / Atom et les injecte dans le workspace 'veille' (collection 'flux-rss').
Applique rigoureusement la règle P5 : statut 'a_verifier' (sas de validation humaine).

Usage :
    poetry run python scripts/harvest_rss.py --url URL [--name NAME]
    poetry run python scripts/harvest_rss.py --preset
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
from knowledge.services.feed_harvester import harvest_remote_feed

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_PRESET_FEEDS = [
    {
        "name": "ANSSI Actualités",
        "url": "https://cyber.gouv.fr/rss/actualites.xml",
        "category": "cybersecurite",
    },
    {
        "name": "CNIL Actualités",
        "url": "https://www.cnil.fr/fr/rss.xml",
        "category": "reglementation",
    },
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "category": "ia",
    },
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Moissonnage de flux RSS vers le workspace veille (Règle P5)")
    parser.add_argument("--url", "-u", default=None, help="URL unique d'un flux RSS/Atom à moissonner")
    parser.add_argument("--name", "-n", default=None, help="Nom logique du flux")
    parser.add_argument("--preset", action="store_true", help="Moissonner la liste des flux de veille par défaut")
    parser.add_argument("--workspace", "-w", default="veille", help="Workspace cible (défaut: veille)")
    parser.add_argument("--collection", "-c", default="flux-rss", help="Collection cible")
    args = parser.parse_args()

    print("=" * 70)
    print("📡 SPRINT 13 — Moissonneur de Veille RSS (Règle P5)")
    print(f" Workspace   : {args.workspace}")
    print(f" Collection  : {args.collection}")
    print(" Règle P5    : auto_approve = False -> Statut 'a_verifier'")
    print("=" * 70)

    feeds_to_harvest = []
    if args.url:
        feeds_to_harvest.append({"name": args.name or "Flux RSS", "url": args.url})
    elif args.preset:
        feeds_to_harvest = DEFAULT_PRESET_FEEDS
    else:
        print("Veuillez spécifier --url <URL> ou --preset.")
        sys.exit(1)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    total_scanned = 0
    total_ingested = 0
    total_skipped = 0

    async with session_factory() as session:
        for feed in feeds_to_harvest:
            print(f"\n[+] Moissonnage du flux : {feed['name']} ({feed['url']})...")
            result = await harvest_remote_feed(
                feed_url=feed["url"],
                db=session,
                feed_name=feed["name"],
                workspace_slug=args.workspace,
                collection_name=args.collection,
            )
            print(f"    - Articles scannés : {result.scanned_entries}")
            print(f"    - Mis en validation (a_verifier) : {result.ingested_count}")
            print(f"    - Ignorés (doublons) : {result.skipped_count}")
            if result.errors:
                for err in result.errors:
                    print(f"    [!] {err}")

            total_scanned += result.scanned_entries
            total_ingested += result.ingested_count
            total_skipped += result.skipped_count

    await engine.dispose()

    print("\n" + "=" * 70)
    print("📊 Bilan Global de Veille :")
    print(f" - Flux traités : {len(feeds_to_harvest)}")
    print(f" - Total articles scannés : {total_scanned}")
    print(f" - Total en attente de validation ('a_verifier') : {total_ingested}")
    print(f" - Total déjà existants (dédupliqués SHA-256) : {total_skipped}")
    print("=" * 70)
    print("✅ Moissonnage terminé avec succès.")


if __name__ == "__main__":
    asyncio.run(main())
