"""
Step 1 — Instrument LLMWiki and seed Phoenix with traces.

TWO MODES:
  --mode seed   (default / offline)
      Injects synthetic traces directly into Phoenix using the Phoenix REST API.
      No AWS credentials needed. Use this when the Lambda is not deployed yet
      or the SSO session has expired. Runs fully offline against localhost Phoenix.

  --mode live
      Calls the deployed llmwiki-query Lambda, records real traces via OTel,
      and lets Phoenix collect them. Requires valid AWS credentials.

Usage:
    python eval/step1_seed_traces.py              # seed mode (offline)
    python eval/step1_seed_traces.py --mode seed  # explicit
    python eval/step1_seed_traces.py --mode live  # live Lambda calls
    python eval/step1_seed_traces.py --mode live --limit 5
"""

import argparse
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── project root on sys.path ───────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from phoenix_config import (
    PHOENIX_ENDPOINT, PROJECT_LAMBDA,
    AWS_PROFILE, AWS_REGION, LAMBDA_NAME, BEDROCK_MODEL_ID,
)

# ── golden seed questions (domain-labelled) ────────────────────────────────
SEED_QA = [
    {
        "question": "What is the standard Sales-to-Service handoff checklist for a new healthcare payer?",
        "domain": "customer-onboarding",
        "answer": "The standard handoff includes: (1) customer classification by product and risk tier, "
                  "(2) executive sponsor and decision authority identification, (3) go-live timeline review, "
                  "(4) data migration and legacy system constraints. [[uc-01-brief]]",
        "context": "The Sales-to-Service playbook requires delivery managers to collect executive sponsor "
                   "information, contractual go-live dates, and product scope before initiating the UC1 agent. "
                   "Source: wiki/skills/wf-UC1-sales-to-service.md",
        "confidence": "high",
        "citations": 3,
    },
    {
        "question": "What are the ARB security requirements for a Facets environment provisioning?",
        "domain": "provisioning",
        "answer": "ARB security requirements include: encryption at rest for all data stores, VPC isolation "
                  "with private subnets, IAM least-privilege roles scoped to specific ARNs, CloudTrail logging "
                  "enabled, and security groups denying all inbound except approved CIDRs. [[sk-03-knowledge-recorder]]",
        "context": "The Facets provisioning runbook specifies that all ARB review items must include "
                   "a security design document covering data classification, network segmentation, and IAM policies. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
        "confidence": "high",
        "citations": 3,
    },
    {
        "question": "What are the required sign-off criteria for SIT completion on a healthcare payer platform?",
        "domain": "testing",
        "answer": "SIT sign-off requires: all P1/P2 defects resolved or risk-accepted, claims volume test passing "
                  "at 110% peak load, EDI 835/837/270/271 validation passing, HIPAA scan with zero critical findings, "
                  "and written sign-off from the customer UAT lead. [[sk-04-template-auto-fill]]",
        "context": "The testing playbook for healthcare payer platforms defines SIT exit criteria as: "
                   "defect density below threshold, transaction validation passing, and compliance scanning complete. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
        "confidence": "high",
        "citations": 4,
    },
    {
        "question": "What data quality checks are required before migrating member enrollment data to QNXT?",
        "domain": "data-migration",
        "answer": "Required DQ checks: duplicate member ID detection, DOB validation against SSN format, "
                  "active coverage date range consistency, plan code mapping validation, and subscriber/dependent "
                  "relationship integrity. All checks must produce a DQ scorecard. [[sk-05-missing-info-radar]]",
        "context": "The data migration runbook specifies pre-migration validation steps for QNXT enrollment data. "
                   "Source: wiki/skills/sk-03-knowledge-recorder.md",
        "confidence": "medium",
        "citations": 2,
    },
    {
        "question": "What monitoring thresholds trigger an escalation during Facets hypercare?",
        "domain": "hypercare",
        "answer": "Escalation is triggered when: claims error rate exceeds 2% over 15 minutes, batch completion "
                  "falls 30+ minutes behind schedule, DB connection pool exhaustion detected, API p95 exceeds 3s, "
                  "or any P1 production incident raised. [[sk-01-customer-briefing-loader]]",
        "context": "The hypercare runbook defines monitoring thresholds for Facets production environments. "
                   "Source: wiki/skills/wf-UC1-sales-to-service.md",
        "confidence": "high",
        "citations": 3,
    },
    {
        "question": "What does the customer education pack include for a QNXT go-live?",
        "domain": "handover",
        "answer": "The QNXT go-live education pack includes: system operations guide, user administration "
                  "procedures, claims inquiry procedures, standard report catalog, escalation matrix, "
                  "and hypercare SLA terms. [[sk-04-template-auto-fill]]",
        "context": "The handover playbook specifies education pack components for QNXT implementations. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
        "confidence": "high",
        "citations": 3,
    },
    {
        "question": "What is the RBAC matrix for a QNXT implementation delivery team?",
        "domain": "identity-access",
        "answer": "The QNXT RBAC matrix: Delivery Manager has read-all + write-project-tracking; "
                  "Config Analyst has write on benefit/provider/member modules; Data Migration Engineer has "
                  "write on data load utilities + read-only production; Security Auditor has read-only + audit log. "
                  "[[sk-01-customer-briefing-loader]]",
        "context": "The identity and access management runbook defines RBAC patterns for QNXT implementation teams. "
                   "Source: wiki/skills/sk-03-knowledge-recorder.md",
        "confidence": "high",
        "citations": 4,
    },
    {
        "question": "What is LLMWiki governance and how does it affect agent performance?",
        "domain": "platform",
        "answer": "LLMWiki governance tracks Bedrock token costs per caller, implements semantic response caching "
                  "to reduce repeat query costs, and enforces per-agent rate limits. Governance adds <5ms overhead "
                  "on cache misses and eliminates Bedrock latency entirely on cache hits (<100ms). "
                  "[[sk-02-knowledge-finder]]",
        "context": "The governance design document describes the cost tracking and caching architecture. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
        "confidence": "high",
        "citations": 3,
    },
    {
        "question": "What are the go/no-go criteria before a Facets production cutover?",
        "domain": "cutover",
        "answer": "Facets cutover go/no-go requires: SIT and E2E sign-off complete, data migration dry run "
                  "within cutover window, rollback procedure documented and tested, ops team trained, monitoring "
                  "dashboards configured, and executive sponsor cutover authorization form signed. "
                  "[[sk-05-missing-info-radar]]",
        "context": "The cutover planning runbook specifies go/no-go criteria for Facets production deployments. "
                   "Source: wiki/skills/wf-UC1-sales-to-service.md",
        "confidence": "high",
        "citations": 4,
    },
    {
        "question": "What instance types are recommended for a TriZetto NetworX production environment?",
        "domain": "provisioning",
        "answer": "NetworX production uses r-series (memory-optimized) for the application tier due to in-memory "
                  "caching, and RDS with Provisioned IOPS for the database tier. Specific sizing depends on "
                  "contracted network size and monthly fee calculation volume. [[sk-02-knowledge-finder]]",
        "context": "The NetworX sizing guide describes instance type selection criteria. "
                   "Source: wiki/skills/sk-02-knowledge-finder.md",
        "confidence": "medium",
        "citations": 2,
    },
    # Two deliberately low-confidence examples to test gap detection
    {
        "question": "What is the TriZetto audit log retention policy for HIPAA compliance?",
        "domain": "compliance",
        "answer": "The wiki does not yet have information about TriZetto audit log retention policies. "
                  "Please upload relevant HIPAA compliance documentation.",
        "context": "",
        "confidence": "low",
        "citations": 0,
    },
    {
        "question": "How does the LLMWiki handle concurrent agent write conflicts?",
        "domain": "platform",
        "answer": "The wiki has limited documentation on concurrent write conflict handling. Based on "
                  "partial context, the contribute Lambda uses DynamoDB conditional writes for index entries. "
                  "[[sk-03-knowledge-recorder]]",
        "context": "The contribute Lambda handler uses DynamoDB put_item for index registration. "
                   "Source: wiki/skills/sk-03-knowledge-recorder.md",
        "confidence": "medium",
        "citations": 1,
    },
]


# ── Seed mode: inject synthetic traces via Phoenix REST API ────────────────
# Uses Phoenix v1 REST API (application/json), not the OTLP protobuf endpoint.
# Endpoints: POST /v1/projects  →  POST /v1/projects/{id}/spans

def _phoenix_request(method: str, path: str, payload: dict = None) -> dict:
    url = f"{PHOENIX_ENDPOINT}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Phoenix {method} {path} → {e.code}: {body}") from e


def _get_or_create_project(project_name: str) -> str:
    """Return the Phoenix project identifier (name), creating it if needed."""
    # List existing projects
    try:
        result = _phoenix_request("GET", "/v1/projects")
        for proj in result.get("data", []):
            if proj.get("name") == project_name:
                return proj["name"]
    except Exception:
        pass
    # Create project
    try:
        _phoenix_request("POST", "/v1/projects", {"name": project_name})
    except RuntimeError as e:
        if "already" not in str(e).lower() and "409" not in str(e):
            raise
    return project_name


def _iso_now() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _iso_offset(seconds: float) -> str:
    import datetime
    dt = datetime.datetime.utcnow() - datetime.timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _seed_trace(qa: dict, project_name: str) -> str:
    """Send one synthetic span to Phoenix via the v1 REST spans API."""
    trace_id = uuid.uuid4().hex
    span_id  = uuid.uuid4().hex[:16]

    span = {
        "name":       "llmwiki.query",
        "context":    {"trace_id": trace_id, "span_id": span_id},
        "span_kind":  "CHAIN",
        "start_time": _iso_offset(2.1),
        "end_time":   _iso_now(),
        "status_code": "OK",
        "attributes": {
            "input.value":               qa["question"],
            "output.value":              qa["answer"],
            "llmwiki.retrieved_context": qa["context"],
            "llmwiki.confidence":        qa["confidence"],
            "llmwiki.domain":            qa["domain"],
            "llmwiki.citation_count":    qa["citations"],
            "llm.model_name":            BEDROCK_MODEL_ID,
            "openinference.span.kind":   "CHAIN",
        },
    }

    _phoenix_request("POST", f"/v1/projects/{project_name}/spans", {"data": [span]})
    return trace_id


def run_seed(project_name: str = PROJECT_LAMBDA, questions: list = None) -> None:
    qs = questions or SEED_QA
    print(f"\n=== Step 1: Seeding {len(qs)} synthetic traces → Phoenix project '{project_name}' ===")
    project_name = _get_or_create_project(project_name)
    ok = fail = 0
    for i, qa in enumerate(qs, 1):
        try:
            trace_id = _seed_trace(qa, project_name)
            conf = qa["confidence"]
            marker = "✓" if conf != "low" else "~"
            print(f"  [{i:02d}] {marker} [{conf:6s}] {qa['domain']:20s} — {qa['question'][:55]}")
            ok += 1
        except Exception as e:
            print(f"  [{i:02d}] ✗ FAILED: {e}")
            fail += 1
        time.sleep(0.05)  # avoid overwhelming the local Phoenix

    print(f"\n  Seeded: {ok} OK, {fail} failed")
    print(f"  View traces → {PHOENIX_ENDPOINT} → Projects → {project_name}")


# ── Live mode: call the deployed Lambda and collect real traces ────────────

def run_live(limit: int = 12) -> None:
    try:
        import boto3
        from tracing import setup_tracing
        from opentelemetry import trace as otel_trace
    except ImportError as e:
        print(f"ERROR: missing dependency — {e}\nRun: pip install -r eval/requirements.txt")
        sys.exit(1)

    tracer = setup_tracing(service_name="llmwiki-query-live", project_name=PROJECT_LAMBDA)
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    lambda_client = session.client("lambda")

    qs = SEED_QA[:limit]
    print(f"\n=== Step 1 (live): Calling Lambda '{LAMBDA_NAME}' for {len(qs)} questions ===")

    for i, qa in enumerate(qs, 1):
        with tracer.start_as_current_span("llmwiki.query") as span:
            span.set_attribute("input.value", qa["question"])
            span.set_attribute("llmwiki.domain", qa["domain"])
            span.set_attribute("openinference.span.kind", "CHAIN")
            try:
                resp = lambda_client.invoke(
                    FunctionName=LAMBDA_NAME,
                    Payload=json.dumps({"q": qa["question"]}).encode(),
                )
                result = json.loads(resp["Payload"].read())
                body = json.loads(result.get("body", "{}"))
                answer = body.get("answer", "")
                confidence = body.get("confidence", "low")
                sources = body.get("sources", [])
                context_text = " ".join(s.get("page_slug", "") for s in sources)

                span.set_attribute("output.value",              answer)
                span.set_attribute("llmwiki.confidence",        confidence)
                span.set_attribute("llmwiki.citation_count",    len(sources))
                span.set_attribute("llmwiki.retrieved_context", context_text[:4000])
                print(f"  [{i:02d}] ✓ [{confidence:6s}] {qa['domain']:20s} — {qa['question'][:55]}")
            except Exception as e:
                span.set_status(otel_trace.StatusCode.ERROR, str(e))
                print(f"  [{i:02d}] ✗ {e}")
        time.sleep(0.2)

    print(f"\n  Traces sent → {PHOENIX_ENDPOINT} → Projects → {PROJECT_LAMBDA}")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed or live-capture LLMWiki traces")
    parser.add_argument("--mode",    choices=["seed", "live"], default="seed")
    parser.add_argument("--limit",   type=int, default=12,
                        help="Number of questions to run (live mode only)")
    parser.add_argument("--project", default=PROJECT_LAMBDA,
                        help="Phoenix project name")
    args = parser.parse_args()

    if args.mode == "live":
        run_live(limit=args.limit)
    else:
        run_seed(project_name=args.project)
