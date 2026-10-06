"""
Script CLI pour synchroniser les finances CPTCopro vers la base de connaissances (Sprint 6).
Usage : poetry run python scripts/cptcopro_adapter.py
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ajout du chemin knowledge-api
sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-api"))

from knowledge.config import settings
from knowledge.services.cptcopro import run_cptcopro_sync

load_dotenv()

async def main():
    print("=" * 60)
    print("MEMENTOMORI - Adaptateur CPTCopro (Comptabilité Copropriété)")
    print("=" * 60)
    count = await run_cptcopro_sync(workspace_slug="copro")
    print(f"Synchronisation CPTCopro réussie : {count} documents financiers indexés.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
