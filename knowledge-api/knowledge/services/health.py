"""Service de vérification de santé complète de l'infrastructure MEMENTOMORI (§14.9)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from knowledge.config import settings
from knowledge.logging import get_logger

logger = get_logger(__name__)


async def check_all_services(db: AsyncSession) -> Dict[str, Any]:
    """
    Exécute les tests de connectivité et de latence pour tous les services de la stack:
    - PostgreSQL (+ pgvector)
    - Redis (Cache & Broker)
    - Paperless-ngx (GED)
    - Authentik (IdP & SSO)
    """
    results: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {}
    }
    has_error = False

    # 1. PostgreSQL
    t0 = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - t0) * 1000, 2)
        results["services"]["postgres"] = {
            "status": "ok",
            "latency_ms": latency,
            "error": None
        }
    except Exception as e:
        has_error = True
        logger.error("health_check_postgres_failed", error=str(e))
        results["services"]["postgres"] = {
            "status": "error",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "error": str(e)
        }

    # 2. Redis
    t0 = time.perf_counter()
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        await r.ping()
        await r.aclose()
        latency = round((time.perf_counter() - t0) * 1000, 2)
        results["services"]["redis"] = {
            "status": "ok",
            "latency_ms": latency,
            "error": None
        }
    except Exception as e:
        has_error = True
        logger.error("health_check_redis_failed", error=str(e))
        results["services"]["redis"] = {
            "status": "error",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "error": str(e)
        }

    # 3. Paperless-ngx
    t0 = time.perf_counter()
    try:
        url = f"{settings.PAPERLESS_URL.rstrip('/')}/api/"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            latency = round((time.perf_counter() - t0) * 1000, 2)
            if resp.status_code < 400 or resp.status_code == 401 or resp.status_code == 403:
                # 401/403 signifie que le serveur web et l'API répondent normalement (nécessite token)
                results["services"]["paperless"] = {
                    "status": "ok",
                    "latency_ms": latency,
                    "error": None
                }
            else:
                has_error = True
                results["services"]["paperless"] = {
                    "status": "error",
                    "latency_ms": latency,
                    "error": f"HTTP {resp.status_code}"
                }
    except Exception as e:
        has_error = True
        logger.warning("health_check_paperless_failed", error=str(e))
        results["services"]["paperless"] = {
            "status": "error",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "error": str(e)
        }

    # 4. Authentik
    t0 = time.perf_counter()
    try:
        # Extraire la base URL d'Authentik
        base_url = settings.AUTHENTIK_ISSUER.split("/application/")[0]
        health_url = f"{base_url.rstrip('/')}/-/health/ready/"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(health_url)
            latency = round((time.perf_counter() - t0) * 1000, 2)
            if resp.status_code == 200:
                results["services"]["authentik"] = {
                    "status": "ok",
                    "latency_ms": latency,
                    "error": None
                }
            else:
                has_error = True
                results["services"]["authentik"] = {
                    "status": "error",
                    "latency_ms": latency,
                    "error": f"HTTP {resp.status_code}"
                }
    except Exception as e:
        has_error = True
        logger.warning("health_check_authentik_failed", error=str(e))
        results["services"]["authentik"] = {
            "status": "error",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "error": str(e)
        }

    results["status"] = "degraded" if has_error else "healthy"
    return results
