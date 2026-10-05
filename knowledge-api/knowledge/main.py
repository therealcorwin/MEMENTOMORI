"""Application FastAPI principale pour knowledge-api (Sprint 3)."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Depends
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from knowledge import __version__
from knowledge.config import settings
from knowledge.logging import setup_logging, get_logger
from knowledge.middleware.cors import setup_cors
from knowledge.middleware.metrics import PrometheusMiddleware
from knowledge.middleware.auth import verify_docs_credentials
from knowledge.routers import (
    health_router,
    search_router,
    answer_router,
    ingest_router,
    admin_router,
    orchestrator_router,
)

# 1. Configuration du logging structuré (B8)
setup_logging(json_logs=settings.JSON_LOGS, log_level=settings.LOG_LEVEL)
logger = get_logger("knowledge.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Cycle de vie de l'application (démarrage et arrêt)."""
    logger.info(
        "knowledge_api_starting",
        version=__version__,
        environment=settings.ENVIRONMENT,
        db_url=settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "configured"
    )
    yield
    logger.info("knowledge_api_shutting_down")


# 2. Création de l'application FastAPI avec docs protégés (§16.11)
app = FastAPI(
    title="MEMENTOMORI Knowledge API",
    description="Plateforme de connaissance multi-projets auto-hébergée (RAG hybride pgvector + tsvector).",
    version=__version__,
    docs_url=None,       # Désactivation par défaut pour protection via Basic Auth
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

# 3. Middleware CORS
setup_cors(app)

# 3b. Middleware métriques HTTP Prometheus (§14.13)
app.add_middleware(PrometheusMiddleware)


# 4. Métriques Prometheus (§14.13, Task 3.14)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# 5. Documentation OpenAPI / Swagger protégée (§16.11, Task 3.18)
@app.get("/docs", include_in_schema=False)
async def get_protected_swagger_ui(_username: str = Depends(verify_docs_credentials)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="MEMENTOMORI Knowledge API - Documentation",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
    )

@app.get("/redoc", include_in_schema=False)
async def get_protected_redoc(_username: str = Depends(verify_docs_credentials)):
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="MEMENTOMORI Knowledge API - ReDoc",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
    )

@app.get("/openapi.json", include_in_schema=False)
async def get_protected_openapi(_username: str = Depends(verify_docs_credentials)):
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    return JSONResponse(content=openapi_schema)

# 6. Enregistrement des routers
app.include_router(health_router)
app.include_router(search_router)
app.include_router(answer_router)
app.include_router(ingest_router)
app.include_router(admin_router)
app.include_router(orchestrator_router)
