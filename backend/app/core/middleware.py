"""HTTP middleware — security headers and request metrics/logging.

Kept separate from ``main.py`` so each middleware is unit-testable and the
app entrypoint stays declarative.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = structlog.get_logger()

# API responses are JSON; the frontend is served by nginx (which sets its own
# headers, incl. CSP for the SPA). These defend the API surface itself.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
# Endpoints where no-store would break interactive docs in dev.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            if name == "Content-Security-Policy" and request.url.path.startswith(_DOCS_PATHS):
                continue
            if name == "Cache-Control" and request.url.path.startswith(_DOCS_PATHS):
                continue
            response.headers.setdefault(name, value)
        return response


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Structured access log + Prometheus counters/histograms per request.

    Prometheus metrics are optional (``METRICS_ENABLED``); the structured
    access log always fires so production has request-level observability
    even without a metrics stack.
    """

    def __init__(self, app: object, metrics_enabled: bool = True) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._metrics_enabled = metrics_enabled
        self._counter = None
        self._histogram = None
        if metrics_enabled:
            try:
                from prometheus_client import Counter, Histogram

                self._counter = Counter(
                    "http_requests_total",
                    "HTTP requests",
                    ["method", "path", "status"],
                )
                self._histogram = Histogram(
                    "http_request_duration_seconds",
                    "HTTP request latency",
                    ["method", "path"],
                )
            except ImportError:
                logger.warning("prometheus_client_missing", metrics="disabled")
                self._metrics_enabled = False

    @staticmethod
    def _route_template(request: Request) -> str:
        """Low-cardinality path label: the route template, not the raw URL."""
        route = request.scope.get("route")
        return getattr(route, "path", request.url.path)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            path = self._route_template(request)
            if not path.endswith(("/health", "/ready", "/metrics")):
                logger.info(
                    "http_request",
                    method=request.method,
                    path=path,
                    status=status_code,
                    duration_ms=round(elapsed * 1000, 2),
                )
            if self._metrics_enabled and self._counter is not None:
                self._counter.labels(request.method, path, str(status_code)).inc()
                self._histogram.labels(request.method, path).observe(elapsed)  # type: ignore[union-attr]
