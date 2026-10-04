"""Configuration de knowledge-api via Pydantic Settings."""

import os
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    JSON_LOGS: bool = False

    # Base de données PostgreSQL + pgvector
    DATABASE_URL: str = Field(
        default="",
        description="URL de connexion asynchrone PostgreSQL"
    )

    # Redis (Queue et cache)
    REDIS_URL: str = Field(
        default="",
        description="URL de connexion Redis"
    )

    # Paperless-ngx
    PAPERLESS_URL: str = "http://localhost:8000"
    PAPERLESS_API_TOKEN: str = ""

    # LLM & Embeddings
    GEMINI_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_MODEL: str = "text-embedding-004"
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-1.5-flash"

    # Authentik OIDC
    AUTHENTIK_ISSUER: str = "http://localhost:9000/application/o/knowledge-api/"
    AUTHENTIK_JWKS_URL: str = "http://localhost:9000/application/o/knowledge-api/jwks/"
    AUTHENTIK_AUDIENCE: str = "knowledge-api"

    # Sécurité & Documentation (§16.11)
    CORS_ORIGINS: List[str] = ["*"]
    DOCS_USERNAME: str = "admin"
    DOCS_PASSWORD: str = ""

    def model_post_init(self, __context) -> None:
        if not self.DATABASE_URL:
            db_pw = os.getenv("KNOWLEDGE_DB_PASSWORD", "")
            self.DATABASE_URL = f"postgresql+asyncpg://knowledge_app:{db_pw}@localhost:5433/knowledge"
        if not self.REDIS_URL:
            redis_pw = os.getenv("REDIS_PASSWORD", "")
            self.REDIS_URL = f"redis://:{redis_pw}@localhost:6380"
        if not self.DOCS_PASSWORD:
            self.DOCS_PASSWORD = os.getenv("DOCS_PASSWORD", "mementomori_admin")
        if not self.PAPERLESS_API_TOKEN:
            self.PAPERLESS_API_TOKEN = os.getenv("PAPERLESS_API_TOKEN", "")

settings = Settings()
