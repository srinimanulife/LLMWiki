"""
Base class for all LLMWiki coded tools.
Handles shared AWS Lambda invocation and sly_data extraction.

Reuses code/lambda/common/llmwiki_common.py when available on PYTHONPATH
(e.g. during Neuro SAN local run from the repo root).
Falls back to inline boto3 invocation when running standalone (e.g. inside Docker).
"""

import json
import logging
import os
import sys
from typing import Any, Dict, Union

logger = logging.getLogger(__name__)

# ── Try to import shared common library (available when PYTHONPATH includes code/lambda/)
try:
    from llmwiki_common import invoke_lambda as _common_invoke
    _HAS_COMMON = True
    logger.debug("Using llmwiki_common.invoke_lambda")
except ImportError:
    _HAS_COMMON = False
    import boto3
    logger.debug("Using inline boto3 Lambda invocation (llmwiki_common not on PYTHONPATH)")

# ── OTel tracing (graceful no-op if packages absent) ─────────────────────────
_OTEL_OK = False
_tracer = None

def _init_otel():
    global _OTEL_OK, _tracer
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider = TracerProvider()
        exporter = OTLPSpanExporter(
            endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("neuro-san-agents")
        _OTEL_OK = True
        logger.info("OTel tracing enabled → %s (project: neuro-san-agents)", endpoint)
    except Exception as exc:
        logger.warning("OTel tracing init failed: %s", exc)

_init_otel()


class LLMWikiBaseTool:
    """
    Shared AWS Lambda invocation logic for all LLMWiki coded tools.

    Call _invoke_skill(function_name, payload) to invoke any LLMWiki Lambda.
    The result is the unwrapped inner body dict (API GW wrapper stripped).

    Sensitive context (customer_id, api_key, engagement_id) is carried in
    sly_data and injected into every Lambda payload WITHOUT entering the LLM context.
    This is Neuro SAN's primary structural defence against prompt injection exfiltration.
    """

    AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    def __init__(self):
        if not _HAS_COMMON:
            self._lambda_client = boto3.client("lambda", region_name=self.AWS_REGION)
        else:
            self._lambda_client = None  # unused when common library available

    def _invoke_skill(self, function_name: str, payload: dict) -> Dict[str, Any]:
        """
        Invoke a Lambda-backed LLMWiki skill and return the unwrapped outputs dict.
        Returns an error dict (with '_error': True) on failure — never raises.
        Wraps the call in an OTel span when OTEL_EXPORTER_OTLP_ENDPOINT is set.
        """
        if _OTEL_OK and _tracer:
            return self._invoke_skill_traced(function_name, payload)
        return self._raw_invoke(function_name, payload)

    def _invoke_skill_traced(self, function_name: str, payload: dict) -> Dict[str, Any]:
        """Instrumented path — only called when _OTEL_OK is True."""
        from opentelemetry import trace as _otel_trace
        question = str(payload.get("q", payload.get("question", payload.get("prompt", ""))))[:500]
        with _tracer.start_as_current_span(function_name) as span:
            span.set_attribute("neuro_san.tool", type(self).__name__)
            span.set_attribute("neuro_san.skill", function_name)
            span.set_attribute("input.value", question)
            span.set_attribute("openinference.span.kind", "CHAIN")
            result = self._raw_invoke(function_name, payload)
            span.set_attribute("output.value", str(result.get("answer", result.get("result", "")))[:500])
            span.set_attribute("neuro_san.error", str(result.get("_error", False)))
            span.set_attribute("neuro_san.confidence", str(result.get("confidence", "")))
            if result.get("_error"):
                span.set_status(_otel_trace.StatusCode.ERROR, str(result.get("error", "")))
            return result

    def _raw_invoke(self, function_name: str, payload: dict) -> Dict[str, Any]:
        """Direct Lambda invocation — no tracing overhead."""
        if _HAS_COMMON:
            result = _common_invoke(function_name, payload, label=function_name)
            if result is None:
                return {"_error": True, "error": f"{function_name} returned None", "status": "error"}
            return result

        # Inline fallback
        try:
            resp   = self._lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload, default=str).encode(),
            )
            raw = json.loads(resp["Payload"].read())
            if raw.get("FunctionError"):
                logger.warning("Lambda %s error: %s", function_name, raw)
                return {"_error": True, "error": str(raw), "status": "error"}
            if "body" in raw:
                body = raw["body"]
                return json.loads(body) if isinstance(body, str) else (body or {})
            return raw
        except Exception as exc:
            logger.warning("Lambda invoke %s failed: %s", function_name, exc)
            return {"_error": True, "error": str(exc), "status": "error"}

    @staticmethod
    def _extract_sly(sly_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract the three protected fields from sly_data.
        These are set by AgentCore at session start and never appear in LLM prompts.
        """
        return {
            "customer_id":   sly_data.get("customer_id", ""),
            "api_key":       sly_data.get("llmwiki_api_key", ""),
            "engagement_id": sly_data.get("engagement_id", ""),
        }
