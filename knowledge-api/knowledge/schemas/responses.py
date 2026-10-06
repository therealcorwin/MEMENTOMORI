"""Modèles Pydantic pour les réponses de l'API."""

import uuid
from typing import Any, List, Optional
from pydantic import BaseModel, Field

class SearchResultItem(BaseModel):
    fragment_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    version: int
    content: str
    score: float
    page_number: Optional[int] = None
    sensitivity: str
    scope: str
    citation_ref: dict[str, Any] = Field(default_factory=dict)

class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResultItem]
    trace_id: Optional[str] = None

class SourceCitation(BaseModel):
    document_id: str
    fragment_id: str
    document_title: str
    version: int
    score: float
    page_number: Optional[int] = None
    sensitivity: str
    scope: str
    citation_ref: dict[str, Any] = Field(default_factory=dict)

class AnswerResponse(BaseModel):
    query: str
    answer: str
    confidence: float
    sources: List[SourceCitation]
    citations: List[str]
    limits: Optional[str] = None
    cached: bool = False
    cache_type: Optional[str] = None
    model: str
    provider: str
    warning: Optional[str] = None
    trace_id: Optional[str] = None
    grounding_score: Optional[float] = None
    grounding_verified: Optional[bool] = None

class HealthResponse(BaseModel):
    status: str
    postgres: str
    redis: str
    paperless: str
    environment: str
    version: str

class AuditLogItem(BaseModel):
    id: int
    principal_id: Optional[uuid.UUID] = None
    principal_name: Optional[str] = None
    principal_type: Optional[str] = None
    workspace_id: Optional[uuid.UUID] = None
    workspace_name: Optional[str] = None
    workspace_slug: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[uuid.UUID] = None
    target_name: Optional[str] = None
    summary: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[Any] = None

class AuditLogResponse(BaseModel):
    total: int
    items: List[AuditLogItem]
    limit: int
    offset: int
