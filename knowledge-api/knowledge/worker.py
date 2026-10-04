"""Worker d'ingestion en arrière-plan (Task 3.8)."""

import asyncio
from knowledge.logging import setup_logging, get_logger
from knowledge.services.ingestion import run_paperless_sync

setup_logging(json_logs=False, log_level="INFO")
logger = get_logger("knowledge.worker")

async def main() -> None:
    logger.info("knowledge_worker_started")
    try:
        count = await run_paperless_sync()
        logger.info("initial_sync_completed", ingested_count=count)
    except Exception as e:
        logger.error("worker_sync_failed", error=str(e))

if __name__ == "__main__":
    asyncio.run(main())
