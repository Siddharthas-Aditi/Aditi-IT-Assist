"""OpenTelemetry setup for distributed tracing and observability."""

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_telemetry() -> None:
    """Initialize OpenTelemetry tracing.

    This is a placeholder for future OpenTelemetry integration.
    When enabled, it will provide:
    - Distributed tracing across services
    - Metrics collection
    - Log correlation with trace IDs
    """
    if settings.APP_ENV == "production":
        logger.info(
            "telemetry_init",
            endpoint=settings.OTEL_EXPORTER_ENDPOINT,
            service_name=settings.OTEL_SERVICE_NAME,
        )
        # TODO(team): Implement OTEL SDK initialization
        # from opentelemetry import trace
        # from opentelemetry.sdk.trace import TracerProvider
        # from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    else:
        logger.info("telemetry_skip", reason="non-production environment")
