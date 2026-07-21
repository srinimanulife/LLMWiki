import importlib.util
import json
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _find_target_file() -> Path:
    rel = Path("code/neuro_san/coded_tools/llmwiki/llmwiki_base_tool.py")
    for parent in Path(__file__).resolve().parents:
        candidate = parent / rel
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find target file at {rel}")


def _load_target_module(monkeypatch, *, common_module=None, boto3_module=None):
    target_file = _find_target_file()

    if common_module is None:
        monkeypatch.delitem(sys.modules, "llmwiki_common", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "llmwiki_common", common_module)

    if boto3_module is None:
        monkeypatch.delitem(sys.modules, "boto3", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "boto3", boto3_module)

    module_name = f"llmwiki_base_tool_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, target_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_module_with_common(monkeypatch, invoke_mock=None):
    common_mod = types.ModuleType("llmwiki_common")
    common_mod.invoke_lambda = invoke_mock or MagicMock()
    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = MagicMock()
    module = _load_target_module(monkeypatch, common_module=common_mod, boto3_module=boto3_mod)
    return module, common_mod


def _load_module_without_common(monkeypatch, lambda_client=None):
    lambda_client = lambda_client or MagicMock()
    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = MagicMock(return_value=lambda_client)
    module = _load_target_module(monkeypatch, common_module=None, boto3_module=boto3_mod)
    return module, boto3_mod, lambda_client


def _make_invoke_response(payload_obj):
    payload_stream = MagicMock()
    payload_stream.read.return_value = json.dumps(payload_obj).encode("utf-8")
    return {"Payload": payload_stream}


class FakeSpan:
    def __init__(self):
        self.attributes = {}
        self.status_calls = []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, *args):
        self.status_calls.append(args)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeTracer:
    def __init__(self, span):
        self.span = span
        self.started_spans = []

    def start_as_current_span(self, name):
        self.started_spans.append(name)
        return self.span


def test_class_aws_region_prefers_aws_region_environment_variable(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")

    module, _ = _load_module_with_common(monkeypatch)

    assert module.LLMWikiBaseTool.AWS_REGION == "eu-central-1"


def test_class_aws_region_defaults_to_us_east_1_when_region_envs_are_missing(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    module, _ = _load_module_with_common(monkeypatch)

    assert module.LLMWikiBaseTool.AWS_REGION == "us-east-1"


def test_init_creates_lambda_client_when_common_library_is_unavailable(monkeypatch):
    fake_lambda_client = MagicMock()
    module, boto3_mod, _ = _load_module_without_common(monkeypatch, lambda_client=fake_lambda_client)
    module.LLMWikiBaseTool.AWS_REGION = "eu-west-1"

    tool = module.LLMWikiBaseTool()

    boto3_mod.client.assert_called_once_with("lambda", region_name="eu-west-1")
    assert tool._lambda_client is fake_lambda_client


def test_init_sets_lambda_client_to_none_when_common_library_is_available(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)

    tool = module.LLMWikiBaseTool()

    assert tool._lambda_client is None


def test_invoke_skill_uses_raw_invoke_when_tracing_is_disabled(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)
    tool = module.LLMWikiBaseTool()
    tool._raw_invoke = MagicMock(return_value={"answer": "ok"})
    tool._invoke_skill_traced = MagicMock()

    monkeypatch.setattr(module, "_OTEL_OK", False)
    monkeypatch.setattr(module, "_tracer", None)

    result = tool._invoke_skill("my-fn", {"q": "hello"})

    assert result == {"answer": "ok"}
    tool._raw_invoke.assert_called_once_with("my-fn", {"q": "hello"})
    tool._invoke_skill_traced.assert_not_called()


def test_invoke_skill_uses_traced_invoke_when_tracing_is_enabled_and_tracer_exists(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)
    tool = module.LLMWikiBaseTool()
    tool._invoke_skill_traced = MagicMock(return_value={"result": "traced"})
    tool._raw_invoke = MagicMock()

    monkeypatch.setattr(module, "_OTEL_OK", True)
    monkeypatch.setattr(module, "_tracer", object())

    result = tool._invoke_skill("my-fn", {"question": "hello"})

    assert result == {"result": "traced"}
    tool._invoke_skill_traced.assert_called_once_with("my-fn", {"question": "hello"})
    tool._raw_invoke.assert_not_called()


def test_invoke_skill_traced_sets_span_attributes_and_error_status_for_error_result(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    span = FakeSpan()
    tracer = FakeTracer(span)
    monkeypatch.setattr(module, "_tracer", tracer)

    otel_trace_mod = types.ModuleType("opentelemetry.trace")
    otel_trace_mod.StatusCode = types.SimpleNamespace(ERROR="ERROR")
    otel_mod = types.ModuleType("opentelemetry")
    otel_mod.trace = otel_trace_mod
    monkeypatch.setitem(sys.modules, "opentelemetry", otel_mod)

    tool._raw_invoke = MagicMock(
        return_value={
            "answer": "y" * 700,
            "_error": True,
            "error": "boom",
            "confidence": 0.42,
        }
    )

    payload = {"q": "x" * 700}
    result = tool._invoke_skill_traced("skill-fn", payload)

    assert result["_error"] is True
    assert tracer.started_spans == ["skill-fn"]
    assert span.attributes["neuro_san.tool"] == type(tool).__name__
    assert span.attributes["neuro_san.skill"] == "skill-fn"
    assert len(span.attributes["input.value"]) == 500
    assert len(span.attributes["output.value"]) == 500
    assert span.attributes["neuro_san.error"] == "True"
    assert span.attributes["neuro_san.confidence"] == "0.42"
    assert span.status_calls == [("ERROR", "boom")]


def test_invoke_skill_traced_uses_prompt_fallback_and_skips_error_status_for_success(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    span = FakeSpan()
    tracer = FakeTracer(span)
    monkeypatch.setattr(module, "_tracer", tracer)

    otel_trace_mod = types.ModuleType("opentelemetry.trace")
    otel_trace_mod.StatusCode = types.SimpleNamespace(ERROR="ERROR")
    otel_mod = types.ModuleType("opentelemetry")
    otel_mod.trace = otel_trace_mod
    monkeypatch.setitem(sys.modules, "opentelemetry", otel_mod)

    tool._raw_invoke = MagicMock(return_value={"result": "done", "confidence": "high"})

    result = tool._invoke_skill_traced("skill-fn", {"prompt": "from prompt"})

    assert result == {"result": "done", "confidence": "high"}
    assert span.attributes["input.value"] == "from prompt"
    assert span.attributes["output.value"] == "done"
    assert span.attributes["neuro_san.error"] == "False"
    assert span.status_calls == []


def test_raw_invoke_returns_common_invoke_result_when_common_library_available(monkeypatch):
    invoke_mock = MagicMock(return_value={"answer": "from-common"})
    module, _ = _load_module_with_common(monkeypatch, invoke_mock=invoke_mock)
    tool = module.LLMWikiBaseTool()

    result = tool._raw_invoke("skill-fn", {"q": "hello"})

    assert result == {"answer": "from-common"}
    invoke_mock.assert_called_once_with("skill-fn", {"q": "hello"}, label="skill-fn")


def test_raw_invoke_returns_error_dict_when_common_invoke_returns_none(monkeypatch):
    invoke_mock = MagicMock(return_value=None)
    module, _ = _load_module_with_common(monkeypatch, invoke_mock=invoke_mock)
    tool = module.LLMWikiBaseTool()

    result = tool._raw_invoke("skill-fn", {"q": "hello"})

    assert result == {
        "_error": True,
        "error": "skill-fn returned None",
        "status": "error",
    }
    invoke_mock.assert_called_once_with("skill-fn", {"q": "hello"}, label="skill-fn")


def test_raw_invoke_with_boto3_returns_raw_payload_when_body_is_missing(monkeypatch):
    module, _, lambda_client = _load_module_without_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    lambda_client.invoke.return_value = _make_invoke_response({"result": "ok"})
    payload = {"q": "hello"}

    result = tool._raw_invoke("skill-fn", payload)

    assert result == {"result": "ok"}
    lambda_client.invoke.assert_called_once_with(
        FunctionName="skill-fn",
        InvocationType="RequestResponse",
        Payload=json.dumps(payload, default=str).encode(),
    )


def test_raw_invoke_with_boto3_parses_json_string_inside_body_field(monkeypatch):
    module, _, lambda_client = _load_module_without_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    lambda_client.invoke.return_value = _make_invoke_response({"body": '{"answer":"parsed"}'})

    result = tool._raw_invoke("skill-fn", {"x": 1})

    assert result == {"answer": "parsed"}


def test_raw_invoke_with_boto3_returns_body_dict_as_is(monkeypatch):
    module, _, lambda_client = _load_module_without_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    lambda_client.invoke.return_value = _make_invoke_response({"body": {"answer": "dict-body"}})

    result = tool._raw_invoke("skill-fn", {"x": 1})

    assert result == {"answer": "dict-body"}


def test_raw_invoke_with_boto3_returns_empty_dict_when_body_is_none(monkeypatch):
    module, _, lambda_client = _load_module_without_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    lambda_client.invoke.return_value = _make_invoke_response({"body": None})

    result = tool._raw_invoke("skill-fn", {"x": 1})

    assert result == {}


def test_raw_invoke_with_boto3_returns_error_when_function_error_is_present(monkeypatch):
    module, _, lambda_client = _load_module_without_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    raw_payload = {"FunctionError": "Unhandled", "detail": "bad"}
    lambda_client.invoke.return_value = _make_invoke_response(raw_payload)

    result = tool._raw_invoke("skill-fn", {"x": 1})

    assert result["_error"] is True
    assert result["status"] == "error"
    assert "FunctionError" in result["error"]


def test_raw_invoke_with_boto3_returns_error_dict_when_lambda_invoke_raises_exception(monkeypatch):
    module, _, lambda_client = _load_module_without_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    lambda_client.invoke.side_effect = RuntimeError("invoke failed")

    result = tool._raw_invoke("skill-fn", {"x": 1})

    assert result == {"_error": True, "error": "invoke failed", "status": "error"}


def test_raw_invoke_with_boto3_serializes_non_json_payload_values_using_default_str(monkeypatch):
    module, _, lambda_client = _load_module_without_common(monkeypatch)
    tool = module.LLMWikiBaseTool()

    class NonSerializable:
        def __str__(self):
            return "serialized-by-str"

    lambda_client.invoke.return_value = _make_invoke_response({"result": "ok"})

    tool._raw_invoke("skill-fn", {"obj": NonSerializable()})

    sent_payload = lambda_client.invoke.call_args.kwargs["Payload"]
    assert b'"obj": "serialized-by-str"' in sent_payload


def test_extract_sly_returns_mapped_values_when_keys_exist(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)

    result = module.LLMWikiBaseTool._extract_sly(
        {
            "customer_id": "cust-1",
            "llmwiki_api_key": "api-1",
            "engagement_id": "eng-1",
        }
    )

    assert result == {
        "customer_id": "cust-1",
        "api_key": "api-1",
        "engagement_id": "eng-1",
    }


def test_extract_sly_returns_empty_strings_for_missing_keys(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)

    result = module.LLMWikiBaseTool._extract_sly({})

    assert result == {"customer_id": "", "api_key": "", "engagement_id": ""}


def test_init_otel_does_nothing_when_endpoint_environment_variable_is_not_set(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    module._OTEL_OK = False
    module._tracer = None

    module._init_otel()

    assert module._OTEL_OK is False
    assert module._tracer is None


def test_init_otel_initializes_provider_exporter_and_tracer_when_dependencies_are_available(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318/")

    fake_provider = MagicMock()
    tracer_provider_ctor = MagicMock(return_value=fake_provider)
    simple_span_processor_ctor = MagicMock(side_effect=lambda exporter: ("ssp", exporter))
    otlp_exporter_ctor = MagicMock(side_effect=lambda endpoint: {"endpoint": endpoint})

    fake_tracer = object()
    trace_mod = types.ModuleType("opentelemetry.trace")
    trace_mod.set_tracer_provider = MagicMock()
    trace_mod.get_tracer = MagicMock(return_value=fake_tracer)

    otel_mod = types.ModuleType("opentelemetry")
    otel_mod.trace = trace_mod

    sdk_mod = types.ModuleType("opentelemetry.sdk")
    sdk_trace_mod = types.ModuleType("opentelemetry.sdk.trace")
    sdk_trace_mod.TracerProvider = tracer_provider_ctor
    sdk_trace_export_mod = types.ModuleType("opentelemetry.sdk.trace.export")
    sdk_trace_export_mod.SimpleSpanProcessor = simple_span_processor_ctor
    sdk_mod.trace = sdk_trace_mod

    exporter_mod = types.ModuleType("opentelemetry.exporter")
    exporter_otlp_mod = types.ModuleType("opentelemetry.exporter.otlp")
    exporter_otlp_proto_mod = types.ModuleType("opentelemetry.exporter.otlp.proto")
    exporter_otlp_http_mod = types.ModuleType("opentelemetry.exporter.otlp.proto.http")
    trace_exporter_mod = types.ModuleType("opentelemetry.exporter.otlp.proto.http.trace_exporter")
    trace_exporter_mod.OTLPSpanExporter = otlp_exporter_ctor

    monkeypatch.setitem(sys.modules, "opentelemetry", otel_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk", sdk_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", sdk_trace_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.export", sdk_trace_export_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter", exporter_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp", exporter_otlp_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto", exporter_otlp_proto_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto.http", exporter_otlp_http_mod)
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        trace_exporter_mod,
    )

    module._OTEL_OK = False
    module._tracer = None

    module._init_otel()

    tracer_provider_ctor.assert_called_once()
    otlp_exporter_ctor.assert_called_once_with(endpoint="http://collector:4318/v1/traces")
    simple_span_processor_ctor.assert_called_once_with({"endpoint": "http://collector:4318/v1/traces"})
    fake_provider.add_span_processor.assert_called_once_with(("ssp", {"endpoint": "http://collector:4318/v1/traces"}))
    trace_mod.set_tracer_provider.assert_called_once_with(fake_provider)
    trace_mod.get_tracer.assert_called_once_with("neuro-san-agents")
    assert module._OTEL_OK is True
    assert module._tracer is fake_tracer


def test_init_otel_swallows_exceptions_and_keeps_tracing_disabled_when_initialization_fails(monkeypatch):
    module, _ = _load_module_with_common(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")

    trace_mod = types.ModuleType("opentelemetry.trace")
    trace_mod.set_tracer_provider = MagicMock()
    trace_mod.get_tracer = MagicMock()

    otel_mod = types.ModuleType("opentelemetry")
    otel_mod.trace = trace_mod

    sdk_mod = types.ModuleType("opentelemetry.sdk")
    sdk_trace_mod = types.ModuleType("opentelemetry.sdk.trace")
    sdk_trace_mod.TracerProvider = MagicMock(side_effect=RuntimeError("provider boom"))
    sdk_trace_export_mod = types.ModuleType("opentelemetry.sdk.trace.export")
    sdk_trace_export_mod.SimpleSpanProcessor = MagicMock()

    trace_exporter_mod = types.ModuleType("opentelemetry.exporter.otlp.proto.http.trace_exporter")
    trace_exporter_mod.OTLPSpanExporter = MagicMock()

    monkeypatch.setitem(sys.modules, "opentelemetry", otel_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk", sdk_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", sdk_trace_mod)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.export", sdk_trace_export_mod)
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        trace_exporter_mod,
    )

    module._OTEL_OK = False
    module._tracer = None

    module._init_otel()

    assert module._OTEL_OK is False
    assert module._tracer is None
