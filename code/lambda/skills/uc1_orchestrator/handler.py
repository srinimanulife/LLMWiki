"""
UC1 Sales-to-Service Orchestrator
Demonstrates how an AgentCore UC1 agent orchestrates the 5 POC skills
in the correct sequence to produce a customer handoff brief.
This Lambda acts as a standalone demo of the skill execution flow.
"""

import json
import os
import time
import boto3
from datetime import datetime, timezone

lambda_client = boto3.client("lambda",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))

SK01_FUNCTION = os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap")
SK02_FUNCTION = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")
SK03_FUNCTION = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")
SK04_FUNCTION = os.environ.get("SK04_FUNCTION", "llmwiki-skill-artifact-resolution")
SK05_FUNCTION = os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection")

AGENT_ID  = "uc1-sales-to-service-orchestrator-v1"
USE_CASE  = "UC1"
DOMAIN    = "customer-onboarding"


def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    customer_id = body.get("customer_id", "").strip()
    if not customer_id:
        return _respond(400, {"error": "customer_id is required"})

    execution_log = []

    # ── STEP 1: SK-01 Customer Briefing Loader ─────────────────────
    print(f"[UC1] STEP 1: SK-01 loading context for {customer_id}")
    sk01_result = _invoke_skill(SK01_FUNCTION, {
        "skill": "ContextBootstrapSkill", "version": "1.0",
        "invoked_by": AGENT_ID,
        "inputs": {"customer_id": customer_id, "use_case": USE_CASE, "agent_id": AGENT_ID},
    })
    sk01_outputs = sk01_result.get("outputs", {})
    customer_status = sk01_outputs.get("customer_status", "no-history")
    playbook = sk01_outputs.get("playbook", {})
    execution_log.append({
        "step": 1, "skill_id": "SK-01",
        "business_name": "Customer Briefing Loader",
        "outcome": f"Customer status: {customer_status}, playbook steps: {len(playbook.get('steps', []))}",
        "latency_ms": sk01_result.get("latency_ms", 0),
    })

    # ── STEP 2: SK-02 Knowledge Finder — S2S handoff process ──────
    print("[UC1] STEP 2: SK-02 querying wiki for S2S handoff process")
    sk02_result = _invoke_skill(SK02_FUNCTION, {
        "skill": "WikiQuerySkill", "version": "1.0",
        "invoked_by": AGENT_ID,
        "inputs": {
            "question":    "What are the key steps in the Sales-to-Service handoff process?",
            "domain":      DOMAIN,
            "customer_id": customer_id,
            "use_case":    USE_CASE,
        },
    })
    sk02_outputs = sk02_result.get("outputs", {})
    confidence  = sk02_outputs.get("confidence", "low")
    answer      = sk02_outputs.get("answer", "")
    action_items = sk02_outputs.get("action_items", [])
    execution_log.append({
        "step": 2, "skill_id": "SK-02",
        "business_name": "Knowledge Finder",
        "outcome": f"confidence={confidence}, action_items={len(action_items)}, pages={sk02_result.get('wiki_pages_used', 0)}",
        "latency_ms": sk02_result.get("latency_ms", 0),
    })

    # ── STEP 3: SK-05 if confidence is low ────────────────────────
    gaps = []
    if confidence == "low":
        print("[UC1] STEP 3: SK-05 gap detection triggered (low confidence)")
        sk05_result = _invoke_skill(SK05_FUNCTION, {
            "skill": "GapDetectionSkill", "version": "1.0",
            "invoked_by": AGENT_ID,
            "inputs": {
                "question":    "What are the key steps in the Sales-to-Service handoff process?",
                "domain":      DOMAIN,
                "use_case":    USE_CASE,
                "customer_id": customer_id,
                "low_confidence_response": sk02_outputs,
            },
        })
        gaps = sk05_result.get("outputs", {}).get("gaps", [])
        execution_log.append({
            "step": 3, "skill_id": "SK-05",
            "business_name": "Missing Info Radar",
            "outcome": f"Detected {len(gaps)} gap(s), blocking={any(g.get('blocking') for g in gaps)}",
            "latency_ms": sk05_result.get("latency_ms", 0),
        })
    else:
        execution_log.append({
            "step": 3, "skill_id": "SK-05",
            "business_name": "Missing Info Radar",
            "outcome": f"Skipped — confidence={confidence}, no gap detection needed",
            "latency_ms": 0,
        })

    # ── STEP 4: SK-02 second query — persona requirements ─────────
    print("[UC1] STEP 4: SK-02 querying for persona template requirements")
    sk02b_result = _invoke_skill(SK02_FUNCTION, {
        "skill": "WikiQuerySkill", "version": "1.0",
        "invoked_by": AGENT_ID,
        "inputs": {
            "question":    "What information is required for a customer persona and onboarding brief?",
            "domain":      DOMAIN,
            "customer_id": customer_id,
            "use_case":    USE_CASE,
        },
    })
    sk02b_outputs = sk02b_result.get("outputs", {})
    execution_log.append({
        "step": 4, "skill_id": "SK-02",
        "business_name": "Knowledge Finder",
        "outcome": f"Persona query: confidence={sk02b_outputs.get('confidence', 'low')}, artifacts={len(sk02b_outputs.get('artifacts_referenced', []))}",
        "latency_ms": sk02b_result.get("latency_ms", 0),
    })

    # ── STEP 5: SK-04 Template Auto-Fill ─────────────────────────
    print("[UC1] STEP 5: SK-04 populating persona template")
    available_ctx = {
        "customer_id":      customer_id,
        "use_case":         USE_CASE,
        "customer_status":  customer_status,
        "handoff_answer":   answer[:500] if answer else "",
        "action_items":     action_items[:5],
        "prior_history":    bool(sk01_outputs.get("prior_contributions", [])),
    }
    sk04_result = _invoke_skill(SK04_FUNCTION, {
        "skill": "ArtifactResolutionSkill", "version": "1.0",
        "invoked_by": AGENT_ID,
        "inputs": {
            "artifact_type":     "persona-template",
            "customer_id":       customer_id,
            "use_case":          USE_CASE,
            "available_context": available_ctx,
        },
    })
    sk04_outputs = sk04_result.get("outputs", {})
    populated_content = sk04_outputs.get("artifact_content", "")
    completion_pct    = sk04_outputs.get("completion_pct", 0)
    missing_fields    = sk04_outputs.get("missing_fields", [])
    execution_log.append({
        "step": 5, "skill_id": "SK-04",
        "business_name": "Template Auto-Fill",
        "outcome": f"Template found={sk04_outputs.get('found', False)}, completion={completion_pct}%, missing_fields={len(missing_fields)}",
        "latency_ms": sk04_result.get("latency_ms", 0),
    })

    # ── STEP 6: SK-03 Knowledge Recorder ─────────────────────────
    print("[UC1] STEP 6: SK-03 writing customer handoff brief to wiki")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    handoff_content = _build_handoff_brief(
        customer_id, today, answer, action_items, playbook,
        populated_content, gaps, missing_fields, completion_pct
    )
    page_slug = f"{customer_id.lower().replace(' ', '-')}-handoff-{today}"

    sk03_result = _invoke_skill(SK03_FUNCTION, {
        "skill": "WikiContributeSkill", "version": "1.0",
        "invoked_by": AGENT_ID,
        "inputs": {
            "page_type":   "customers",
            "page_slug":   page_slug,
            "content":     handoff_content,
            "agent_id":    AGENT_ID,
            "customer_id": customer_id,
            "use_case":    USE_CASE,
            "human_review_required": False,
        },
    })
    sk03_outputs = sk03_result.get("outputs", {})
    execution_log.append({
        "step": 6, "skill_id": "SK-03",
        "business_name": "Knowledge Recorder",
        "outcome": f"status={sk03_outputs.get('status', 'unknown')}, s3_uri={sk03_outputs.get('s3_uri', '')}",
        "latency_ms": sk03_result.get("latency_ms", 0),
    })

    total_latency_ms = int((time.time() - t0) * 1000)

    return _respond(200, {
        "customer_id":        customer_id,
        "use_case":           USE_CASE,
        "agent_id":           AGENT_ID,
        "handoff_brief_slug": page_slug,
        "handoff_s3_uri":     sk03_outputs.get("s3_uri", ""),
        "wiki_indexed":       sk03_outputs.get("status") == "indexed",
        "confidence":         confidence,
        "action_items":       action_items,
        "missing_fields":     missing_fields,
        "gaps_detected":      gaps,
        "template_completion_pct": completion_pct,
        "total_latency_ms":   total_latency_ms,
        "skill_execution_log": execution_log,
        "skills_used": ["SK-01", "SK-02", "SK-04", "SK-03"]
                       + (["SK-05"] if confidence == "low" else []),
        "summary": (
            f"UC1 handoff brief generated for {customer_id}. "
            f"Template {completion_pct}% complete. "
            f"{len(missing_fields)} field(s) require human input. "
            f"Page written to wiki for UC2 agent to read."
        ),
    })


def _invoke_skill(fn_name: str, payload: dict) -> dict:
    try:
        resp = lambda_client.invoke(
            FunctionName=fn_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if "body" in raw:
            inner = raw["body"]
            return json.loads(inner) if isinstance(inner, str) else (inner or {})
        return raw
    except Exception as e:
        print(f"WARN: skill invoke {fn_name} failed: {e}")
        return {"status": "error", "outputs": {}, "latency_ms": 0}


def _build_handoff_brief(customer_id, today, answer, action_items,
                          playbook, artifact_content, gaps, missing_fields,
                          completion_pct) -> str:
    gaps_section = ""
    if gaps:
        gaps_list = "\n".join(f"- [{g.get('gap_type','gap')}] {g.get('title','')} — {g.get('human_prompt','')}"
                              for g in gaps)
        gaps_section = f"\n## Knowledge Gaps\n\n{gaps_list}\n"

    missing_section = ""
    if missing_fields:
        missing_list = "\n".join(f"- {f}" for f in missing_fields)
        missing_section = f"\n## Missing Information (Requires Human Input)\n\n{missing_list}\n"

    action_section = ""
    if action_items:
        action_list = "\n".join(f"- {a}" for a in action_items)
        action_section = f"\n## Action Items\n\n{action_list}\n"

    steps_section = ""
    steps = playbook.get("steps", [])
    if steps:
        step_list = "\n".join(
            f"- **Step {s.get('step',i+1)}: {s.get('title','')}** — {s.get('description','')}"
            for i, s in enumerate(steps[:5])
        )
        steps_section = f"\n## UC1 Playbook Steps\n\n{step_list}\n"

    return f"""---
title: Customer Handoff Brief — {customer_id}
date: {today}
tags: [customer, handoff, UC1, sales-to-service]
customer_id: {customer_id}
use_case_tags: [UC1]
domain: customer-onboarding
contributing_agent: {AGENT_ID}
status: active
template_completion_pct: {completion_pct}
---

# Customer Handoff Brief — {customer_id}

*Generated by UC1 Sales-to-Service Agent on {today}*
*This page is the input for UC2 Environment Provisioning Agent.*

## Sales-to-Service Handoff Summary

{answer[:800] if answer else "No handoff information available from wiki — see knowledge gaps below."}
{action_section}{steps_section}
## Customer Persona Template

{artifact_content[:2000] if artifact_content else "Persona template not yet available. Ingest persona-template.md to enable auto-fill."}
{missing_section}{gaps_section}
---
*Next agent: UC2 Environment Provisioning — reads this page to begin BOM and infrastructure setup.*
"""


def _respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=str),
    }
