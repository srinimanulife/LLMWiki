"""
Step 1 helper — OpenTelemetry / OpenInference tracing setup.

Import this at the top of any Lambda handler or local script to send spans
to the self-hosted Phoenix container.

All OTel imports are lazy — if opentelemetry is not installed, setup_tracing()
returns a no-op stub tracer so the rest of the code still runs.

Usage (local script):
    from tracing import setup_tracing
    tracer = setup_tracing(service_name="llmwiki-query-local")

Usage (Lambda cold start, bundled):
    from eval.tracing import setup_tracing
    setup_tracing()
"""

import os
import sys

from phoenix_config import PHOENIX_COLLECTOR, PROJECT_LAMBDA

_initialized = False


class _NoopSpan:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def set_attribute(self, *a): pass
    def set_status(self, *a): pass


class _NoopTracer:
    def start_as_current_span(self, name, **kw):
        return _NoopSpan()


def setup_tracing(
    service_name: str = "llmwiki-query",
    project_name: str = PROJECT_LAMBDA,
    collector_endpoint: str = PHOENIX_COLLECTOR,
    use_simple_processor: bool = False,
):
    """
    Configure the global OTel TracerProvider to export to Phoenix.
    Returns a real Tracer when opentelemetry is installed, or a no-op stub.
    """
    global _initialized

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError:
        print("WARN: opentelemetry not installed — tracing disabled (install eval/requirements.txt)")
        return _NoopTracer()

    try:
        from openinference.instrumentation.bedrock import BedrockInstrumentor
        _bedrock_ok = True
    except ImportError:
        _bedrock_ok = False

    if not _initialized:
        headers = {"x-phoenix-project-name": project_name}
        exporter = OTLPSpanExporter(
            endpoint=collector_endpoint,
            insecure=True,
            headers=headers,
        )
        provider = TracerProvider()
        processor = (SimpleSpanProcessor(exporter)
                     if use_simple_processor
                     else BatchSpanProcessor(exporter))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        if _bedrock_ok:
            BedrockInstrumentor().instrument()

        _initialized = True

    return trace.get_tracer(service_name)
