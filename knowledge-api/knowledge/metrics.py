"""Métriques Prometheus custom pour knowledge-api (§14.13).

Ce module centralise toutes les métriques Prometheus exposées par l'API.
Elles sont enregistrées au niveau module (singleton) et réutilisées partout.
"""

from prometheus_client import Counter, Histogram, Gauge

# ---------------------------------------------------------------------------
# Métriques HTTP (instrumentées via middleware dans main.py)
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "http_requests_total",
    "Nombre total de requêtes HTTP reçues",
    ["method", "handler", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Durée des requêtes HTTP en secondes",
    ["method", "handler"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ---------------------------------------------------------------------------
# Métriques LLM (§14.13)
# ---------------------------------------------------------------------------

llm_requests_total = Counter(
    "llm_requests_total",
    "Nombre total de requêtes LLM",
    ["provider", "model", "request_type", "workspace"],
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "Latence des requêtes LLM en secondes",
    ["provider", "model", "request_type"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Tokens consommés par les requêtes LLM",
    ["provider", "model", "direction"],  # direction: input | output
)

llm_errors_total = Counter(
    "llm_errors_total",
    "Erreurs survenues lors des appels LLM",
    ["provider", "model", "error_type"],
)

llm_confidence_score = Histogram(
    "llm_confidence_score",
    "Score de confiance des réponses générées",
    ["workspace"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

llm_fallback_total = Counter(
    "llm_fallback_total",
    "Nombre de basculements vers un provider de secours",
    ["from_provider", "to_provider"],
)

# ---------------------------------------------------------------------------
# Métriques RAG / Recherche
# ---------------------------------------------------------------------------

search_requests_total = Counter(
    "search_requests_total",
    "Nombre total de requêtes de recherche hybride",
    ["workspace", "mode"],  # mode: search | answer | orchestrate
)

search_latency_seconds = Histogram(
    "search_latency_seconds",
    "Latence des recherches hybrides en secondes",
    ["workspace", "mode"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

cache_hits_total = Counter(
    "cache_hits_total",
    "Nombre de réponses servies depuis le cache intelligent",
    ["workspace"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Nombre de requêtes non trouvées dans le cache",
    ["workspace"],
)

# ---------------------------------------------------------------------------
# Métriques d'ingestion
# ---------------------------------------------------------------------------

ingestion_documents_total = Counter(
    "ingestion_documents_total",
    "Nombre total de documents ingérés",
    ["workspace", "source", "status"],  # status: success | duplicate | error
)

ingestion_fragments_total = Counter(
    "ingestion_fragments_total",
    "Nombre total de fragments créés lors de l'ingestion",
    ["workspace"],
)

# ---------------------------------------------------------------------------
# Gauges d'état
# ---------------------------------------------------------------------------

documents_total_gauge = Gauge(
    "documents_total",
    "Nombre total de documents indexés",
    ["workspace"],
)

fragments_total_gauge = Gauge(
    "fragments_total",
    "Nombre total de fragments en base",
    ["workspace"],
)
