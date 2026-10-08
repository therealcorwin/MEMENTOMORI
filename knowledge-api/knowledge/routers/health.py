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

@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
async def check_health(
    db: AsyncSession = Depends(get_db),
    detailed: bool = False
) -> HealthResponse:
    """Sonde de santé pour knowledge-api.
    
    Par défaut (usage public / sondes) : renvoie uniquement {"status": "ok"}
    pour empêcher toute fuite d'information sur la pile technique interne (anti-reconnaissance OWASP).
    Si detailed=True : renvoie le détail des dépendances (diagnostic interne).
    """
    # 1. PostgreSQL + pgvector
    pg_ok = True
    pg_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        pg_ok = False
        pg_status = "error"

    # 2. Redis
    redis_ok = True
    redis_status = "ok"
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        await r.ping()
        await r.aclose()
    except Exception as e:
        redis_ok = False
        redis_status = "error"

    overall = "ok" if (pg_ok and redis_ok) else "degraded"

    if not detailed:
        return HealthResponse(status=overall)

    # 3. Paperless-ngx (uniquement si detailed=True)
    paperless_status = "ok"
    try:
        url = f"{settings.PAPERLESS_URL.rstrip('/')}/api/"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                paperless_status = f"http_{resp.status_code}"
    except Exception:
        paperless_status = "unreachable"

    return HealthResponse(
        status=overall,
        postgres=pg_status,
        redis=redis_status,
        paperless=paperless_status,
        environment=settings.ENVIRONMENT,
        version=__version__
    )
