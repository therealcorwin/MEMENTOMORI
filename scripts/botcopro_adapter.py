"""
Script CLI pour synchroniser les données Botcopro vers la base de connaissances (Sprint 11, Tâche 11.2).
Usage : poetry run python scripts/botcopro_adapter.py [--mock] [--workspace copro]
"""

import argparse
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ajout du chemin knowledge-api
sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-api"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from knowledge.services.botcopro import run_botcopro_sync


async def main():
    parser = argparse.ArgumentParser(description="Synchronisation Botcopro MariaDB -> MEMENTOMORI")
    parser.add_argument("--workspace", default="copro", help="Slug du workspace cible (défaut: copro)")
    parser.add_argument("--mock", action="store_true", help="Forcer l'utilisation des données représentatives simulées")
    args = parser.parse_args()

    mode_str = "SIMULATION (MOCK)" if args.mock else "MARIADB RÉEL"
    print("=" * 70)
    print(f"MEMENTOMORI - Pipeline Botcopro : Incidents, AG & Sondages ({mode_str})")
    print(f"Workspace cible : {args.workspace}")
    print("=" * 70)

    count = await run_botcopro_sync(workspace_slug=args.workspace, force_mock=args.mock)
    print(f"\n[SUCCÈS] Synchronisation Botcopro terminée : {count} documents indexés avec succès.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

