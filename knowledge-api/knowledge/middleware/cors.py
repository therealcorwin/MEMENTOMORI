"""Configuration du middleware CORS."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from knowledge.config import settings

def setup_cors(app: FastAPI) -> None:
    """Ajoute le middleware CORS à l'application FastAPI."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
