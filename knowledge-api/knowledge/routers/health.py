"""Router de santé pour knowledge-api (§14.9)."""

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from knowledge import __version__
from knowledge.config import settings
from knowledge.dependencies import get_db
from knowledge.schemas import HealthResponse

router = APIRouter(tags=["Health"])

@router.get("/health", response_model=HealthResponse)
async def check_health(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Vérifie la santé des dépendances critiques (PostgreSQL, Redis, Paperless)."""
    # 1. PostgreSQL + pgvector
    pg_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        pg_status = f"error: {str(e)}"

    # 2. Redis
    redis_status = "ok"
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        await r.ping()
        await r.aclose()
    except Exception as e:
        redis_status = f"error: {str(e)}"

    # 3. Paperless-ngx
    paperless_status = "ok"
    try:
        url = f"{settings.PAPERLESS_URL.rstrip('/')}/api/"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                paperless_status = f"http_{resp.status_code}"
    except Exception as e:
        paperless_status = f"unreachable: {str(e)}"

    overall = "ok" if (pg_status == "ok" and redis_status == "ok") else "degraded"

    return HealthResponse(
        status=overall,
        postgres=pg_status,
        redis=redis_status,
        paperless=paperless_status,
        environment=settings.ENVIRONMENT,
        version=__version__
    )
