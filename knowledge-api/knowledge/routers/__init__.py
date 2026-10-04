"""Export des routers FastAPI."""

from knowledge.routers.health import router as health_router
from knowledge.routers.search import router as search_router
from knowledge.routers.answer import router as answer_router
from knowledge.routers.ingest import router as ingest_router
from knowledge.routers.admin import router as admin_router
from knowledge.routers.orchestrator import router as orchestrator_router

__all__ = [
    "health_router",
    "search_router",
    "answer_router",
    "ingest_router",
    "admin_router",
    "orchestrator_router",
]
