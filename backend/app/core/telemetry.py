"""Observability wiring — request metrics (always-available) + optional OTEL.

Two layers, independently switchable:

1. **Metrics + access logs** — ``RequestMetricsMiddleware``
   (``app/core/middleware.py``) emits a structured ``http_request`` log line
   per request and Prometheus counters/histograms, exposed at
   ``GET /api/v1/health/metrics`` when ``METRICS_ENABLED=true``. No external
   infrastructure required; this is the production baseline.

2. **Distributed tracing** — opt-in via ``OTEL_ENABLED=true``. Initializes
   the OpenTelemetry SDK with an OTLP exporter pointed at
   ``OTEL_EXPORTER_ENDPOINT``. The OTEL packages are an optional extra —
   if they aren't installed, tracing is skipped with a clear log line rather
   than crashing the app (tracing must never take down the API).
"""

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_telemetry() -> None:
    """Initialize optional OpenTelemetry tracing (metrics need no setup)."""
    if not settings.OTEL_ENABLED:
        logger.info("telemetry_tracing_disabled", metrics_enabled=settings.METRICS_ENABLED)
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "telemetry_otel_packages_missing",
            hint="uv add opentelemetry-sdk opentelemetry-exporter-otlp",
        )
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_ENDPOINT))
    )
    trace.set_tracer_provider(provider)
    logger.info("telemetry_tracing_enabled", endpoint=settings.OTEL_EXPORTER_ENDPOINT)
