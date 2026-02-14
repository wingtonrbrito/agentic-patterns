"""
AgentOS OpenTelemetry Setup

Production observability:
- Traces for agent workflows (spans per step)
- Metrics for latency, token usage, confidence scores
- Logs structured with trace context
"""
from __future__ import annotations
from typing import Optional
import os


def setup_otel(
    service_name: str = "agentos",
    endpoint: Optional[str] = None,
):
    """Initialize OpenTelemetry with OTLP exporter."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        otlp_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        return trace.get_tracer(service_name)

    except ImportError:
        # Graceful degradation if OTEL not installed
        return None


def create_agent_span(tracer, agent_name: str, query: str):
    """Create a span for an agent execution."""
    if tracer is None:
        return None
    return tracer.start_span(
        f"agent.{agent_name}",
        attributes={
            "agent.name": agent_name,
            "agent.query_length": len(query),
        },
    )
