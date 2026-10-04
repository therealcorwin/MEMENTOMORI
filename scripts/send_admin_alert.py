"""
Script CLI pour tester l'envoi des alertes administrateur Telegram (Sprint 6, Tâche 6.7).
Usage : poetry run python scripts/send_admin_alert.py [info|warning|critical] "Titre" "Message"
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ajout du chemin knowledge-api
sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-api"))

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from knowledge.services.notifier import send_admin_alert, AlertLevel

load_dotenv()

async def main():
    level_arg = sys.argv[1] if len(sys.argv) > 1 else "warning"
    title_arg = sys.argv[2] if len(sys.argv) > 2 else "Test de Notification Proactive"
    msg_arg = sys.argv[3] if len(sys.argv) > 3 else "Ceci est un test du système d'alerte proactive Telegram de MEMENTOMORI."

    print("=" * 60)
    print(f"MEMENTOMORI - Envoi d'alerte [{level_arg.upper()}] : '{title_arg}'")
    print("=" * 60)

    success = await send_admin_alert(
        level=level_arg,
        title=title_arg,
        message=msg_arg,
        context={"service": "knowledge-api", "module": "ingestion", "worker_status": "active"}
    )
    if success:
        print("Alerte traitée avec succès !")
    else:
        print("Erreur lors de l'envoi de l'alerte.")

if __name__ == "__main__":
    asyncio.run(main())
