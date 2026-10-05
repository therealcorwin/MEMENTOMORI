"""Middleware Prometheus pour l'instrumentation automatique HTTP (§14.13)."""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from knowledge.metrics import http_requests_total, http_request_duration_seconds


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Enregistre automatiquement les métriques HTTP pour chaque requête."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Résolution du handler (path template) pour éviter l'explosion de cardinalité
        handler = "unknown"
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                handler = getattr(route, "path", handler)
                break

        # Exclusion des endpoints techniques non pertinents pour les métriques
        if request.url.path in ("/metrics", "/health", "/healthz"):
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        http_requests_total.labels(
            method=request.method,
            handler=handler,
            status=str(response.status_code),
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            handler=handler,
        ).observe(duration)

        return response
