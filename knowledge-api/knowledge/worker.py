"""Worker d'ingestion en arrière-plan (Task 3.8)."""

import asyncio
from knowledge.logging import setup_logging, get_logger
from knowledge.services.ingestion import run_paperless_sync

setup_logging(json_logs=False, log_level="INFO")
logger = get_logger("knowledge.worker")

async def main() -> None:
    logger.info("knowledge_worker_started")
    while True:
        try:
            count = await run_paperless_sync()
            logger.info("worker_sync_completed", ingested_count=count)
        except Exception as e:
            logger.error("worker_sync_failed", error=str(e))
        # Synchronisation périodique toutes les 60 secondes
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
