"""Azure Application Insights TraceSink (Microsoft AI stack observability).

Forwards every SpanRecord to Azure Monitor as a custom event so Meridian's
agent traces appear alongside Azure's native telemetry in App Insights.

Wired additively alongside DbTraceSink in runner.py — the Postgres sink is
unchanged. Install azure-monitor-opentelemetry to activate:

    uv add azure-monitor-opentelemetry

Configure via env:
    APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=...
"""

from __future__ import annotations

import logging

from meridian.observability.tracing import SpanRecord

logger = logging.getLogger(__name__)

_configured = False


def _ensure_configured(connection_string: str) -> bool:
    """Configure the Azure Monitor exporter once per process."""
    global _configured
    if _configured:
        return True
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=connection_string)
        _configured = True
        return True
    except ImportError:
        logger.warning(
            "azure-monitor-opentelemetry not installed; "
            "install with: uv add azure-monitor-opentelemetry"
        )
        return False


class AzureAppInsightsSink:
    """TraceSink that forwards spans to Azure Application Insights.

    Uses OpenTelemetry's Azure Monitor exporter so spans show up as
    custom events in App Insights with all attributes preserved.
    Falls back silently if the package is not installed, so the worker
    starts cleanly even in local dev without Azure credentials.
    """

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string
        self._active = _ensure_configured(connection_string)

    async def record(self, span: SpanRecord) -> None:
        if not self._active:
            return
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer("meridian")
            with tracer.start_as_current_span(span.name) as otel_span:
                otel_span.set_attribute("meridian.task_id", span.task_id)
                otel_span.set_attribute("meridian.kind", span.kind)
                otel_span.set_attribute("meridian.turn_num", span.turn_num)
                otel_span.set_attribute("meridian.outcome", span.outcome)
                otel_span.set_attribute("meridian.cost_usd", span.cost_usd)
                otel_span.set_attribute("meridian.summary", span.summary[:256])
                for k, v in (span.attributes or {}).items():
                    otel_span.set_attribute(k, str(v)[:512])
        except Exception as exc:
            logger.debug("AzureAppInsightsSink.record failed: %s", exc)
