"""Modèles Pydantic pour les requêtes entrantes."""

import uuid
from typing import Optional
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    workspace_id: uuid.UUID = Field(..., description="Identifiant unique du workspace ciblé")
    query: str = Field(..., min_length=2, max_length=1000, description="Requête de recherche en langage naturel")
    top_k: int = Field(5, ge=1, le=20, description="Nombre maximum de résultats souhaités")
    trace_id: Optional[str] = Field(None, description="Identifiant de corrélation pour les logs")

class AnswerRequest(BaseModel):
    workspace_id: uuid.UUID = Field(..., description="Identifiant unique du workspace ciblé")
    query: str = Field(..., min_length=2, max_length=1000, description="Question en langage naturel")
    top_k: int = Field(5, ge=1, le=10, description="Nombre de fragments documentaires injectés dans le contexte")
    use_cache: bool = Field(True, description="Active la vérification et l'invalidation du cache intelligent (§16.9)")
    trace_id: Optional[str] = Field(None, description="Identifiant de corrélation pour les logs")

class IngestRequest(BaseModel):
    workspace_slug: str = Field("copro-jardins", description="Slug du workspace destinataire")
    collection_name: str = Field("Archives Copropriété", description="Nom de la collection")
    sync_paperless: bool = Field(True, description="Déclencher la synchronisation des documents Paperless")

class FeedbackRequest(BaseModel):
    query_id: uuid.UUID = Field(..., description="ID de la requête à laquelle le feedback se rapporte")
    workspace_id: uuid.UUID = Field(..., description="ID du workspace")
    question: str = Field(..., description="Question originale")
    answer: str = Field(..., description="Réponse évaluée")
    rating: str = Field(..., pattern="^(good|bad|wrong)$", description="Note : good, bad, wrong")
    user_id: Optional[int] = Field(None, description="ID utilisateur éventuel (Telegram)")
