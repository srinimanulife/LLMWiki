import json
import os
import re
import time
import uuid
import boto3
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# ── AWS clients ───────────────────────────────────────────────────────────────
_region = os.environ.get("AWS_REGION", "us-east-1")

dynamodb      = boto3.resource("dynamodb", region_name=_region)
lambda_client = boto3.client("lambda",    region_name=_region)
bedrock       = boto3.client("bedrock-runtime", region_name=_region)
s3_client     = boto3.client("s3",        region_name=_region)

# ── Environment / config ──────────────────────────────────────────────────────
HARNESS_RUNS_TABLE = os.environ.get("HARNESS_RUNS_TABLE", "llmwiki-harness-runs")
WORKSPACE_TABLE    = os.environ.get("WORKSPACE_TABLE",    "llmwiki-workspace-files")
MODEL_ID           = os.environ.get("BEDROCK_MODEL_ID",   "us.anthropic.claude-sonnet-4-6")
WIKI_BUCKET        = os.environ.get("WIKI_BUCKET",        "")

SK01_FUNCTION     = os.environ.get("SK01_FUNCTION",     "llmwiki-skill-context-bootstrap")
SK02_FUNCTION     = os.environ.get("SK02_FUNCTION",     "llmwiki-skill-wiki-query")
SK03_FUNCTION     = os.environ.get("SK03_FUNCTION",     "llmwiki-skill-wiki-contribute")
SK04_FUNCTION     = os.environ.get("SK04_FUNCTION",     "llmwiki-skill-artifact-resolution")
SK05_FUNCTION     = os.environ.get("SK05_FUNCTION",     "llmwiki-skill-gap-detection")
PLAYBOOK_FUNCTION = os.environ.get("PLAYBOOK_FUNCTION", "llmwiki-playbook")

TTL_30_DAYS = 30 * 86400


# ════════════════════════════════════════════════════════════════════════════
# Custom exceptions
# ════════════════════════════════════════════════════════════════════════════

class _PhaseError(Exception):
    """Raised by any phase to abort the workflow."""
    def __init__(self, phase: int, message: str):
        super().__init__(message)
        self.phase   = phase
        self.message = message


# ════════════════════════════════════════════════════════════════════════════
# DynamoDB helpers
# ════════════════════════════════════════════════════════════════════════════

def _init_harness_run(table, engagement_id: str, run_id: str, payload: dict) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    item = {
        "engagement_id": engagement_id,
        "run_id":        run_id,
        "status":        "running",
        "current_phase": 1,
        "started_at":    now_iso,
        "updated_at":    now_iso,
        "phase_results": json.dumps({}),
        "ttl":           int(time.time()) + TTL_30_DAYS,
    }
    item.update(payload)
    table.put_item(Item=item)


def _update_harness_run(table, engagement_id: str, run_id: str, updates: dict) -> None:
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_expr   = "SET " + ", ".join(f"#{k}=:{k}" for k in updates)
    expr_names = {f"#{k}": k for k in updates}
    expr_vals  = {f":{k}": v for k, v in updates.items()}
    table.update_item(
        Key={"engagement_id": engagement_id, "run_id": run_id},
        UpdateExpression=set_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_vals,
    )


def _find_paused_run(table, engagement_id: str) -> dict:
    try:
        resp  = table.query(
            KeyConditionExpression="engagement_id = :eid",
            ExpressionAttributeValues={":eid": engagement_id},
        )
        items = sorted(resp.get("Items", []), key=lambda x: x.get("started_at", ""), reverse=True)
        for item in items:
            if item.get("status") == "paused":
                return item
    except Exception as exc:
        print(f"WARN: _find_paused_run error: {exc}")
    return {}


def _find_latest_run(table, engagement_id: str) -> dict:
    """Return the most recent run for an engagement regardless of status."""
    try:
        resp  = table.query(
            KeyConditionExpression="engagement_id = :eid",
            ExpressionAttributeValues={":eid": engagement_id},
        )
        items = sorted(resp.get("Items", []), key=lambda x: x.get("started_at", ""), reverse=True)
        if items:
            return items[0]
    except Exception as exc:
        print(f"WARN: _find_latest_run error: {exc}")
    return {}


def _save_phase(table, engagement_id: str, run_id: str,
                phase_num: int, phase_data: dict, all_phases: dict) -> None:
    """Write per-phase result + advance current_phase in DynamoDB."""
    try:
        all_phases[f"phase{phase_num}"] = phase_data
        _update_harness_run(table, engagement_id, run_id, {
            "current_phase": phase_num,
            "phase_results": json.dumps(all_phases, default=str),
        })
    except Exception as exc:
        print(f"WARN: _save_phase({phase_num}) failed (non-fatal): {exc}")


def _write_workspace(engagement_id: str, file_path: str, content: str) -> None:
    try:
        table = dynamodb.Table(WORKSPACE_TABLE)
        table.put_item(Item={
            "engagement_id": engagement_id,
            "file_path":     file_path,
            "content":       content,
            "updated_at":    datetime.now(timezone.utc).isoformat(),
            "ttl":           int(time.time()) + TTL_30_DAYS,
        })
    except Exception as exc:
        print(f"WARN: _write_workspace failed for {file_path}: {exc}")


# ════════════════════════════════════════════════════════════════════════════
# Invocation helpers
# ════════════════════════════════════════════════════════════════════════════

def _invoke_skill(function_name: str, payload: dict, timeout_ms: int = 60000) -> dict:
    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        raw = response["Payload"].read()
        result = json.loads(raw)
        if isinstance(result, dict) and "body" in result:
            body = result["body"]
            if isinstance(body, str):
                return json.loads(body)
            return body
        return result
    except Exception as exc:
        raise RuntimeError(f"_invoke_skill({function_name}) failed: {exc}") from exc


def _bedrock_call(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    converse_kwargs = {
        "modelId": model_id_for_call(),
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
    }
    if system:
        converse_kwargs["system"] = [{"text": system}]
    response = bedrock.converse(**converse_kwargs)
    return response["output"]["message"]["content"][0]["text"]


def model_id_for_call() -> str:
    return MODEL_ID


def _parse_json_from_text(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


# ════════════════════════════════════════════════════════════════════════════
# Response helpers
# ════════════════════════════════════════════════════════════════════════════

def _ok(body: dict) -> dict:
    return {
        "statusCode": 200,
        "headers":    {"Content-Type": "application/json"},
        "body":       json.dumps(body, default=str),
    }


def _error_response(message: str, partial: dict) -> dict:
    return {
        "statusCode": 500,
        "headers":    {"Content-Type": "application/json"},
        "body":       json.dumps({"status": "error", "error": message, **partial}, default=str),
    }


# ════════════════════════════════════════════════════════════════════════════
# Lambda entry point
# ════════════════════════════════════════════════════════════════════════════

def lambda_handler(event: dict, context) -> dict:
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or event)

    customer_id   = body.get("customer_id", "").strip()
    customer_name = body.get("customer_name", customer_id)
    product       = body.get("product", "")
    sow_reference = body.get("sow_reference", "")
    action        = body.get("action", "")
    human_context = body.get("human_context", "")

    table = dynamodb.Table(HARNESS_RUNS_TABLE)

    if action == "get_status":
        engagement_id = body.get("engagement_id", customer_id)
        run = _find_latest_run(table, engagement_id)
        if not run:
            return _ok({"status": "not_found", "engagement_id": engagement_id})
        raw_pr = run.get("phase_results", "{}")
        phase_results = json.loads(raw_pr) if isinstance(raw_pr, str) else (raw_pr or {})
        phases_done = len([k for k in phase_results if k != "error"])
        p8 = phase_results.get("phase8", {})
        return _ok({
            "status":              run.get("status", "running"),
            "run_id":              run.get("run_id", ""),
            "current_phase":       run.get("current_phase", 1),
            "phases_done":         phases_done,
            "phase_results":       phase_results,
            "total_latency_ms":    run.get("total_latency_ms", 0),
            "report_download_url": p8.get("report_download_url", ""),
        })

    if not customer_id:
        return _ok({"status": "error", "error": "customer_id is required"})

    engagement_id = customer_id
    run_id = f"run-{engagement_id}-{int(time.time())}"

    # Check for paused run waiting for human input
    paused_run = _find_paused_run(table, engagement_id)
    if paused_run and human_context:
        # Resume with human context
        run_id = paused_run["run_id"]
        prior  = json.loads(paused_run.get("phase_results", "{}"))
        phase1 = prior.get("phase1", {})
        phase2 = prior.get("phase2", {})

        _update_harness_run(table, engagement_id, run_id,
                             {"status": "running", "current_phase": 3})
        accumulated = {"phase1": phase1, "phase2": phase2}
        try:
            phase3 = _phase3_human_input(
                table, engagement_id, run_id, phase2, phase1, human_context, prior
            )
            _save_phase(table, engagement_id, run_id, 3, phase3, accumulated)

            phase4 = _phase4_load_delivery_playbook(engagement_id)
            _save_phase(table, engagement_id, run_id, 4, phase4, accumulated)

            phase5 = _phase5_risk_analysis(customer_id, product, phase3, engagement_id)
            _save_phase(table, engagement_id, run_id, 5, phase5, accumulated)

            phase6 = _phase6_gap_detection(phase5, engagement_id, customer_id, product)
            _save_phase(table, engagement_id, run_id, 6, phase6, accumulated)

            phase7 = _phase7_template_population(engagement_id, customer_id, phase1, phase2, phase3, phase5, phase6)
            _save_phase(table, engagement_id, run_id, 7, phase7, accumulated)

            phase8 = _phase8_write_handoff_report(
                engagement_id, customer_id, customer_name, product, sow_reference,
                phase1, phase2, phase3, phase4, phase5, phase6, phase7, run_id,
            )
            _save_phase(table, engagement_id, run_id, 8, phase8, accumulated)
        except _PhaseError as exc:
            _update_harness_run(table, engagement_id, run_id,
                                 {"status": "error", "error": str(exc)})
            return _error_response(str(exc), {"run_id": run_id, "phase": exc.phase})

        total_ms = int((time.time() - t0) * 1000)
        final_status = "completed_with_gaps" if accumulated.get("phase6", {}).get("gaps_blocking") else "completed"
        _update_harness_run(table, engagement_id, run_id, {
            "status":           final_status,
            "current_phase":    8,
            "total_latency_ms": total_ms,
            "phase_results":    json.dumps(accumulated, default=str),
        })
        return _ok(_build_completion_summary(run_id, customer_id, customer_name,
                                              8, total_ms, accumulated,
                                              phase8.get("report_download_url", "")))

    if paused_run and not human_context:
        return _ok({
            "status":        "paused",
            "run_id":        paused_run["run_id"],
            "current_phase": paused_run.get("current_phase", 3),
            "question":      (
                "Please provide: executive sponsor name, go-live target quarter, "
                "any prior implementation attempts, and key stakeholders."
            ),
        })

    # Fresh start
    _init_harness_run(table, engagement_id, run_id, body)

    try:
        phase1 = _phase1_customer_wiki_lookup(engagement_id, customer_id)
        _update_harness_run(table, engagement_id, run_id,
                             {"current_phase": 2,
                              "phase_results": json.dumps({"phase1": phase1})})

        phase2 = _phase2_engagement_classification(phase1)
        _update_harness_run(table, engagement_id, run_id, {
            "current_phase": 3,
            "phase_results": json.dumps({"phase1": phase1, "phase2": phase2}),
        })

        # Pause for human input
        _update_harness_run(table, engagement_id, run_id, {"status": "paused"})
        return _ok({
            "status":        "paused",
            "run_id":        run_id,
            "current_phase": 3,
            "question":      (
                "Please provide: executive sponsor name, go-live target quarter, "
                "any prior implementation attempts, and key stakeholders."
            ),
            "risk_tier":     phase2.get("risk_tier"),
            "complexity":    phase2.get("implementation_complexity"),
        })

    except _PhaseError as exc:
        _update_harness_run(table, engagement_id, run_id,
                             {"status": "error", "error": str(exc)})
        return _error_response(str(exc), {"run_id": run_id, "phase": exc.phase})


# ════════════════════════════════════════════════════════════════════════════
# Phase implementations
# ════════════════════════════════════════════════════════════════════════════

def _phase1_customer_wiki_lookup(engagement_id: str, customer_id: str) -> dict:
    """Step 1: Customer Wiki Lookup via SK-01 / PLAYBOOK_FUNCTION."""
    try:
        result = _invoke_skill(PLAYBOOK_FUNCTION, {
            "action":      "get_customer",
            "customer_id": customer_id,
        })
    except Exception as exc:
        raise _PhaseError(1, f"Customer wiki lookup failed: {exc}") from exc

    pages_found      = int(result.get("pages_found", 0))
    customer_status  = result.get("customer_status", "no-history" if pages_found == 0 else "active")
    key_facts        = result.get("key_facts", [])
    overview         = result.get("overview", "")
    products_in_scope = result.get("products_in_scope", [])

    return {
        "customer_status":  customer_status,
        "pages_found":      pages_found,
        "key_facts":        key_facts,
        "overview":         overview,
        "products_in_scope": products_in_scope,
    }


def _phase2_engagement_classification(phase1: dict) -> dict:
    """Step 2: Engagement Classification via direct Bedrock call."""
    pages_found = int(phase1.get("pages_found", 0))
    new_customer_note = (
        "IMPORTANT: This customer has NO prior history. Default risk_tier=HIGH and "
        "implementation_complexity=HIGH unless data clearly indicates otherwise.\n"
        if pages_found == 0 else ""
    )

    system_prompt = (
        "You are a healthcare IT delivery classification expert. "
        "Classify engagements based on customer data and return ONLY valid JSON."
    )

    prompt = f"""{new_customer_note}
You are classifying a new Sales-to-Service handoff engagement.

Customer data summary:
{json.dumps(phase1, indent=2)}

Classify this engagement and return EXACTLY this JSON (no other text):
{{
  "customer_type": "payer|provider|pharmacy|government",
  "products": ["list of products in scope"],
  "risk_tier": "HIGH|MEDIUM|LOW",
  "go_live_urgency": "HIGH|MEDIUM|LOW",
  "implementation_complexity": "HIGH|MEDIUM|LOW",
  "rationale": "2-3 sentence explanation of risk classification"
}}
"""

    try:
        raw = _bedrock_call(prompt, system=system_prompt, max_tokens=1024)
        classification = _parse_json_from_text(raw)
    except Exception as exc:
        raise _PhaseError(2, f"Engagement classification failed: {exc}") from exc

    if not classification:
        raise _PhaseError(2, "Engagement classification returned empty JSON")

    # Enforce new-customer rule
    if pages_found == 0:
        classification["risk_tier"] = "HIGH"
        classification.setdefault("implementation_complexity", "HIGH")

    return {
        "customer_type":             classification.get("customer_type", "payer"),
        "products":                  classification.get("products", phase1.get("products_in_scope", [])),
        "risk_tier":                 classification.get("risk_tier", "HIGH"),
        "go_live_urgency":           classification.get("go_live_urgency", "MEDIUM"),
        "implementation_complexity": classification.get("implementation_complexity", "HIGH"),
        "rationale":                 classification.get("rationale", ""),
    }


def _phase3_human_input(
    harness_table,
    engagement_id: str,
    run_id: str,
    phase2: dict,
    phase1: dict,
    human_context: str,
    phase_results: dict,
) -> dict:
    """Step 3: Human Input — Sales Team Q&A (pause/resume)."""

    risk_tier   = phase2.get("risk_tier", "HIGH")
    complexity  = phase2.get("implementation_complexity", "HIGH")
    products    = phase2.get("products", [])

    # ── Resume path ──────────────────────────────────────────────────────────
    if human_context:
        summary = human_context[:500]
        return {
            "status":        "answered",
            "human_context": human_context,
            "summary":       summary,
        }

    # ── First invocation — generate questions and pause ───────────────────────
    candidate_questions = [
        "Who is the executive sponsor? Do they have full decision authority, "
        "or is there an approval committee?",
        "What is the contractual go-live date, and are there penalty clauses "
        "if it is missed?",
    ]
    if risk_tier == "HIGH":
        candidate_questions.insert(
            0,
            "Were there any prior implementation attempts with this customer? "
            "What were the outcomes?",
        )
    if complexity == "HIGH":
        candidate_questions.append(
            "What are the data migration or legacy system constraints that "
            "delivery should know about?"
        )

    questions = candidate_questions[:3]
    question_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))

    products_str = ", ".join(products) if products else "N/A"
    context_note = (
        f"Customer overview: {phase1.get('overview', 'No prior history')}\n"
        if phase1.get("overview") else ""
    )

    phase3_question = (
        f"Sales Team — please answer the following questions about this engagement "
        f"(products: {products_str}, risk: {risk_tier}, complexity: {complexity}):\n\n"
        f"{context_note}"
        f"{question_text}"
    )

    _update_harness_run(harness_table, engagement_id, run_id, {
        "status":           "paused",
        "current_phase":    3,
        "phase3_question":  phase3_question,
        "phase_results":    json.dumps(phase_results),
    })

    return {"__paused__": True, "phase3_question": phase3_question}


def _phase4_load_delivery_playbook(engagement_id: str) -> dict:
    """Step 4: Load Delivery Playbook via SK-01 / PLAYBOOK_FUNCTION."""
    try:
        result = _invoke_skill(PLAYBOOK_FUNCTION, {
            "action":   "get_playbook",
            "use_case": "UC1",
        })
        steps        = result.get("steps", [])
        pages_loaded = int(result.get("pages_loaded", 0))
        return {
            "steps":        steps,
            "pages_loaded": pages_loaded,
            "playbook_steps": len(steps),
        }
    except Exception as exc:
        print(f"WARN: Phase 4 playbook load failed (non-blocking): {exc}")
        return {"steps": [], "pages_loaded": 0, "playbook_steps": 0}


def _phase5_risk_analysis(
    customer_id: str,
    product: str,
    phase3: dict,
    engagement_id: str,
) -> dict:
    """Step 5: Risk Analysis via SK-02 (WikiQuerySkill)."""
    summary = phase3.get("summary", "")
    product_str = product or "healthcare platform"

    query = (
        f"What are the key delivery risks and success factors for a new "
        f"{product_str} implementation for a healthcare payer? "
        f"Customer context: {summary}"
    )

    try:
        result = _invoke_skill(SK02_FUNCTION, {
            "query":         query,
            "domain_filter": "customer-onboarding",
            "customer_id":   customer_id,
        })
        confidence      = result.get("confidence", "low")
        answer          = result.get("answer", "")
        action_items    = result.get("action_items", [])
        wiki_page_count = int(result.get("wiki_page_count", 0))
        return {
            "confidence":      confidence,
            "answer":          answer,
            "action_items":    action_items,
            "wiki_page_count": wiki_page_count,
        }
    except Exception as exc:
        print(f"WARN: Phase 5 risk analysis failed (non-blocking): {exc}")
        return {
            "confidence":      "low",
            "answer":          "",
            "action_items":    [],
            "wiki_page_count": 0,
        }


def _phase6_gap_detection(
    phase5: dict,
    engagement_id: str,
    customer_id: str,
    product: str,
) -> dict:
    """Step 6: Knowledge Gap Detection via SK-05 (GapDetectionSkill)."""
    confidence = phase5.get("confidence", "low")
    if confidence == "high":
        return {
            "gaps":          [],
            "gap_count":     0,
            "blocking_count": 0,
            "sub_agents_run": 0,
            "skipped":       True,
        }

    action_items = phase5.get("action_items", [])
    answer       = phase5.get("answer", "")

    # Derive gap questions
    gap_questions = [ai for ai in action_items if "?" in ai]

    if not gap_questions:
        # Synthesize gap questions via Bedrock
        if answer:
            try:
                synth_prompt = (
                    f"Given this risk analysis:\n{answer}\n\n"
                    "Generate 1-3 specific knowledge gap questions that a delivery team "
                    "needs answered. Return ONLY a JSON array of question strings, "
                    "e.g. [\"Question 1?\", \"Question 2?\"]"
                )
                raw = _bedrock_call(synth_prompt, max_tokens=512)
                match = re.search(r"\[.*?\]", raw, re.DOTALL)
                if match:
                    gap_questions = json.loads(match.group(0))
            except Exception as exc:
                print(f"WARN: Gap question synthesis failed: {exc}")

    if not gap_questions:
        gap_questions = [
            "What implementation standards apply to this product integration?",
            "What data migration constraints exist for this customer environment?",
        ]

    gap_questions = gap_questions[:3]

    all_gaps       = []
    sub_agents_run = 0

    for question in gap_questions:
        try:
            result = _invoke_skill(SK05_FUNCTION, {
                "question":    question,
                "customer_id": customer_id,
                "product":     product or "healthcare platform",
                "domain":      "customer-onboarding",
                "engagement_id": engagement_id,
            })
            gaps = result.get("gaps", [])
            all_gaps.extend(gaps)
            sub_agents_run += 1
        except Exception as exc:
            print(f"WARN: Phase 6 SK-05 call failed for question '{question}': {exc}")

    blocking_count = sum(1 for g in all_gaps if g.get("blocking", False))

    return {
        "gaps":           all_gaps,
        "gap_count":      len(all_gaps),
        "blocking_count": blocking_count,
        "sub_agents_run": sub_agents_run,
        "skipped":        False,
    }


def _phase7_template_population(
    engagement_id: str,
    customer_id: str,
    phase1: dict,
    phase2: dict,
    phase3: dict,
    phase5: dict,
    phase6: dict,
) -> dict:
    """Step 7: Template Population via SK-04 (ArtifactResolutionSkill)."""
    context_bundle = {
        "customer_id":               customer_id,
        "customer_status":           phase1.get("customer_status", "unknown"),
        "key_facts":                 phase1.get("key_facts", []),
        "products":                  phase2.get("products", []),
        "risk_tier":                 phase2.get("risk_tier", "HIGH"),
        "go_live_urgency":           phase2.get("go_live_urgency", "MEDIUM"),
        "implementation_complexity": phase2.get("implementation_complexity", "HIGH"),
        "rationale":                 phase2.get("rationale", ""),
        "human_context":             phase3.get("human_context", ""),
        "risk_answer":               phase5.get("answer", ""),
        "action_items":              phase5.get("action_items", []),
        "gaps":                      phase6.get("gaps", []),
        "blocking_gaps":             phase6.get("blocking_count", 0),
        "artifact_name":             "persona-template",
    }

    try:
        result = _invoke_skill(SK04_FUNCTION, {
            "action":         "populate_template",
            "artifact_name":  "persona-template",
            "context_bundle": context_bundle,
            "engagement_id":  engagement_id,
        })
        return {
            "found":             result.get("found", False),
            "completion_pct":    int(result.get("completion_pct", 0)),
            "populated_fields":  result.get("populated_fields", []),
            "missing_fields":    result.get("missing_fields", []),
        }
    except Exception as exc:
        print(f"WARN: Phase 7 template population failed (non-blocking): {exc}")
        return {
            "found":            False,
            "completion_pct":   0,
            "populated_fields": [],
            "missing_fields":   [],
        }


def _phase8_write_handoff_report(
    engagement_id: str,
    customer_id: str,
    customer_name: str,
    product: str,
    sow_reference: str,
    phase1: dict,
    phase2: dict,
    phase3: dict,
    phase4: dict,
    phase5: dict,
    phase6: dict,
    phase7: dict,
    run_id: str,
) -> dict:
    """Step 8: Write Handoff Report to wiki + S3."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    year_str  = datetime.now(timezone.utc).strftime("%Y")

    # 1. Build wiki markdown
    md_content = _build_handoff_markdown(
        customer_id, customer_name, product, sow_reference, run_id,
        phase1, phase2, phase3,
    )

    # 2. Index via SK-03
    wiki_page_path = f"customers/{customer_id}-harness-handoff-{year_str}"
    wiki_result    = {}
    try:
        wiki_result = _invoke_skill(SK03_FUNCTION, {
            "inputs": {
                "page_type":   "customers",
                "page_slug":   f"{customer_id}-harness-handoff-{year_str}",
                "content":     md_content,
                "customer_id": customer_id,
                "use_case":    "UC1",
                "agent_id":    "uc1-harness",
            },
            "invoked_by": "uc1-harness",
        })
    except Exception as exc:
        print(f"WARN: Phase 8 SK-03 wiki index failed: {exc}")

    # Persist markdown to workspace
    _write_workspace(engagement_id, f"{wiki_page_path}.md", md_content)

    report_html_key = f"wiki/reports/{customer_id}-handoff-report-{today_str}.html"
    report_txt_key  = f"wiki/reports/{customer_id}-handoff-report-{today_str}.txt"
    wiki_md_key     = f"wiki/customers/{customer_id}-harness-handoff-{year_str}.md"

    download_url    = ""

    if WIKI_BUCKET:
        # 3. HTML report
        html_content = _build_report_html(
            customer_id, customer_name, product, sow_reference, today_str,
            phase1, phase2, phase3, phase4, phase5, phase6, phase7, run_id,
        )
        txt_content = _build_report_text(
            customer_id, customer_name, product, sow_reference, today_str,
            phase1, phase2, phase3, phase4, phase5, phase6, phase7,
        )

        s3_errors = []
        for key, body, ct in [
            (report_html_key, html_content, "text/html"),
            (report_txt_key,  txt_content,  "text/plain"),
            (wiki_md_key,     md_content,   "text/markdown"),
        ]:
            try:
                s3_client.put_object(
                    Bucket=WIKI_BUCKET,
                    Key=key,
                    Body=body.encode("utf-8"),
                    ContentType=ct,
                )
            except Exception as exc:
                s3_errors.append(f"{key}: {exc}")
                print(f"WARN: S3 put_object failed for {key}: {exc}")

        # 5. Presigned URL (12-hour)
        try:
            download_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": WIKI_BUCKET, "Key": report_html_key},
                ExpiresIn=43200,
            )
        except Exception as exc:
            print(f"WARN: Presigned URL generation failed: {exc}")
    else:
        print("WARN: WIKI_BUCKET not set; skipping S3 writes")

    return {
        "wiki_page_path":       wiki_page_path,
        "wiki_indexed":         wiki_result.get("status") == "success",
        "report_html_s3_key":   report_html_key,
        "report_txt_s3_key":    report_txt_key,
        "wiki_md_s3_key":       wiki_md_key,
        "report_download_url":  download_url,
    }


# ════════════════════════════════════════════════════════════════════════════
# Report builders
# ════════════════════════════════════════════════════════════════════════════

def _tier_badge_color(tier: str) -> str:
    return {"HIGH": "#c0392b", "MEDIUM": "#e67e22", "LOW": "#27ae60"}.get(tier.upper(), "#7f8c8d")


def _build_report_html(
    customer_id: str,
    customer_name: str,
    product: str,
    sow_reference: str,
    date_str: str,
    phase1: dict,
    phase2: dict,
    phase3: dict,
    phase4: dict,
    phase5: dict,
    phase6: dict,
    phase7: dict,
    run_id: str = "",
) -> str:
    risk_tier    = phase2.get("risk_tier", "HIGH")
    complexity   = phase2.get("implementation_complexity", "HIGH")
    urgency      = phase2.get("go_live_urgency", "MEDIUM")
    cust_type    = phase2.get("customer_type", "N/A")
    products_str = ", ".join(phase2.get("products", [])) or product or "N/A"
    rationale    = phase2.get("rationale", "")

    pages_found    = int(phase1.get("pages_found", 0))
    cust_status    = phase1.get("customer_status", "unknown")
    overview       = phase1.get("overview", "No prior customer history available.")
    key_facts      = phase1.get("key_facts", [])

    human_ctx      = phase3.get("human_context", "")
    summary_text   = phase3.get("summary", human_ctx[:500] if human_ctx else "")

    playbook_steps = int(phase4.get("playbook_steps", 0))
    playbook_note  = (
        f"{playbook_steps} steps loaded"
        if playbook_steps > 0
        else "Playbook not yet seeded"
    )

    risk_conf      = phase5.get("confidence", "low")
    risk_answer    = phase5.get("answer", "No risk analysis available.")
    action_items   = phase5.get("action_items", [])
    wiki_pages     = int(phase5.get("wiki_page_count", 0))

    gaps           = phase6.get("gaps", [])
    gap_count      = int(phase6.get("gap_count", 0))
    blocking_count = int(phase6.get("blocking_count", 0))
    gaps_skipped   = phase6.get("skipped", False)

    tmpl_found     = phase7.get("found", False)
    completion_pct = int(phase7.get("completion_pct", 0))
    pop_fields     = phase7.get("populated_fields", [])
    miss_fields    = phase7.get("missing_fields", [])

    risk_color   = _tier_badge_color(risk_tier)
    cplx_color   = _tier_badge_color(complexity)
    urgency_color = _tier_badge_color(urgency)

    def badge(label: str, value: str, color: str) -> str:
        return (
            f'<div class="kpi-item">'
            f'<span class="kpi-label">{label}</span>'
            f'<span class="kpi-value" style="background:{color}">{value}</span>'
            f'</div>'
        )

    kpi_bar = (
        badge("Risk Tier", risk_tier, risk_color)
        + badge("Complexity", complexity, cplx_color)
        + badge("Go-Live Urgency", urgency, urgency_color)
        + badge("Customer Type", cust_type.title(), "#2980b9")
        + badge("Wiki Pages", str(pages_found), "#8e44ad")
        + badge("Gaps Found", str(gap_count), "#c0392b" if gap_count > 0 else "#27ae60")
        + badge("Blocking Gaps", str(blocking_count), "#c0392b" if blocking_count > 0 else "#27ae60")
        + badge("Template Fill", f"{completion_pct}%", "#16a085")
    )

    key_facts_html = (
        "<ul>" + "".join(f"<li>{f}</li>" for f in key_facts) + "</ul>"
        if key_facts
        else "<p>No key facts extracted.</p>"
    )

    action_html = (
        "<ol>" + "".join(f"<li>{a}</li>" for a in action_items) + "</ol>"
        if action_items
        else "<p>No action items identified.</p>"
    )

    gaps_html_parts = []
    for g in gaps:
        blocking_label = (
            '<span style="color:#c0392b;font-weight:bold"> [BLOCKING]</span>'
            if g.get("blocking") else ""
        )
        gaps_html_parts.append(
            f'<div class="gap-item">'
            f'<strong>{g.get("title", "Unknown Gap")}</strong>{blocking_label}<br>'
            f'<em>Type:</em> {g.get("gap_type", "N/A")}<br>'
            f'<em>Human Prompt:</em> {g.get("human_prompt", "")}'
            f'</div>'
        )
    gaps_html = (
        "".join(gaps_html_parts)
        if gaps_html_parts
        else "<p>No knowledge gaps detected.</p>"
    )

    miss_html = (
        "<ul>" + "".join(f"<li>{f}</li>" for f in miss_fields) + "</ul>"
        if miss_fields else "<p>None identified.</p>"
    )
    pop_html = (
        "<ul>" + "".join(f"<li>{f}</li>" for f in pop_fields) + "</ul>"
        if pop_fields else "<p>None yet.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sales-to-Service Handoff — {customer_name}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px;
          background: #f5f7fa; color: #2c3e50; }}
  .header {{ background: linear-gradient(135deg, #1a252f, #2c3e50); color: white;
             padding: 24px 32px; border-radius: 10px; margin-bottom: 24px; }}
  .header h1 {{ margin: 0 0 8px 0; font-size: 1.6rem; }}
  .header p  {{ margin: 0; opacity: 0.75; font-size: 0.9rem; }}
  .kpi-bar   {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }}
  .kpi-item  {{ background: white; border-radius: 8px; padding: 12px 18px;
                box-shadow: 0 2px 6px rgba(0,0,0,.08); min-width: 120px; }}
  .kpi-label {{ display: block; font-size: 0.72rem; color: #7f8c8d;
                text-transform: uppercase; letter-spacing: .05em; }}
  .kpi-value {{ display: block; font-size: 1.1rem; font-weight: 700;
                color: white; background: #2c3e50; border-radius: 4px;
                padding: 2px 8px; margin-top: 4px; text-align: center; }}
  .section   {{ background: white; border-radius: 10px; padding: 20px 28px;
                box-shadow: 0 2px 6px rgba(0,0,0,.08); margin-bottom: 20px; }}
  .section h2 {{ margin: 0 0 14px 0; font-size: 1.1rem; color: #1a252f;
                 border-bottom: 2px solid #eaecee; padding-bottom: 8px; }}
  .gap-item  {{ background: #fdfefe; border-left: 4px solid #c0392b;
                padding: 10px 14px; margin-bottom: 10px; border-radius: 0 6px 6px 0; }}
  .footer    {{ text-align: center; color: #95a5a6; font-size: 0.8rem; margin-top: 32px; }}
</style>
</head>
<body>
<div class="header">
  <h1>Sales-to-Service Handoff: {customer_name}</h1>
  <p>SOW: {sow_reference} &nbsp;|&nbsp; Product: {product} &nbsp;|&nbsp;
     Generated: {date_str} &nbsp;|&nbsp; Run ID: {run_id}</p>
</div>

<div class="kpi-bar">{kpi_bar}</div>

<div class="section">
  <h2>Customer Overview</h2>
  <p><strong>Status:</strong> {cust_status.title()} &nbsp;|&nbsp;
     <strong>Wiki Pages:</strong> {pages_found}</p>
  <p>{overview}</p>
  {key_facts_html}
</div>

<div class="section">
  <h2>Risk &amp; Complexity Assessment</h2>
  <p><strong>Risk Tier:</strong> {risk_tier} &nbsp;|&nbsp;
     <strong>Complexity:</strong> {complexity} &nbsp;|&nbsp;
     <strong>Go-Live Urgency:</strong> {urgency}</p>
  <p><strong>Customer Type:</strong> {cust_type.title()} &nbsp;|&nbsp;
     <strong>Products:</strong> {products_str}</p>
  <p>{rationale}</p>
</div>

<div class="section">
  <h2>Sales Context (Human Input)</h2>
  <p>{summary_text or '<em>No additional context provided.</em>'}</p>
</div>

<div class="section">
  <h2>Implementation Playbook</h2>
  <p>{playbook_note}</p>
</div>

<div class="section">
  <h2>Risk Q&amp;A</h2>
  <p><strong>Confidence:</strong> {risk_conf.title()}</p>
  <p>{risk_answer}</p>
  {action_html}
</div>

<div class="section">
  <h2>Knowledge Gaps</h2>
  {'<p><em>Gap detection skipped (low-confidence answer not available).</em></p>' if gaps_skipped else gaps_html}
</div>

<div class="section">
  <h2>Template Completion</h2>
  <p><strong>Completion:</strong> {completion_pct}% &nbsp;|&nbsp;
     <strong>Found:</strong> {'Yes' if tmpl_found else 'No'}</p>
  <p><strong>Populated fields:</strong></p>{pop_html}
  <p><strong>Missing fields:</strong></p>{miss_html}
</div>

<div class="footer">
  <p>Generated by LLMWiki &middot; {customer_id} &middot; {date_str}</p>
</div>
</body>
</html>"""


def _build_report_text(
    customer_id: str,
    customer_name: str,
    product: str,
    sow_reference: str,
    date_str: str,
    phase1: dict,
    phase2: dict,
    phase3: dict,
    phase4: dict,
    phase5: dict,
    phase6: dict,
    phase7: dict,
) -> str:
    lines = [
        "=" * 70,
        f"SALES-TO-SERVICE HANDOFF REPORT",
        f"Customer : {customer_name} ({customer_id})",
        f"SOW      : {sow_reference}",
        f"Product  : {product}",
        f"Date     : {date_str}",
        "=" * 70,
        "",
        "RISK & COMPLEXITY",
        f"  Risk Tier  : {phase2.get('risk_tier', 'N/A')}",
        f"  Complexity : {phase2.get('implementation_complexity', 'N/A')}",
        f"  Urgency    : {phase2.get('go_live_urgency', 'N/A')}",
        f"  Rationale  : {phase2.get('rationale', '')}",
        "",
        "CUSTOMER OVERVIEW",
        f"  {phase1.get('overview', 'No prior history.')}",
        "",
        "SALES CONTEXT",
        f"  {phase3.get('summary', phase3.get('human_context', 'Not provided.')[:400])}",
        "",
        "RISK Q&A",
        f"  Confidence: {phase5.get('confidence', 'low')}",
        f"  {phase5.get('answer', 'N/A')}",
        "",
        "ACTION ITEMS",
    ]
    for item in phase5.get("action_items", []):
        lines.append(f"  - {item}")
    lines += [
        "",
        "KNOWLEDGE GAPS",
    ]
    for g in phase6.get("gaps", []):
        blocking = " [BLOCKING]" if g.get("blocking") else ""
        lines.append(f"  [{g.get('gap_type', 'unknown')}]{blocking} {g.get('title', '')}")
        lines.append(f"    → {g.get('human_prompt', '')}")
    lines += [
        "",
        "TEMPLATE COMPLETION",
        f"  {phase7.get('completion_pct', 0)}% complete",
        "=" * 70,
    ]
    return "\n".join(lines)


def _build_handoff_markdown(
    customer_id: str,
    customer_name: str,
    product: str,
    sow_reference: str,
    run_id: str,
    phase1: dict,
    phase2: dict,
    phase3: dict,
) -> str:
    return "\n".join([
        f"# Sales-to-Service Handoff: {customer_name}",
        f"",
        f"**SOW:** {sow_reference}  ",
        f"**Product:** {product}  ",
        f"**Customer ID:** {customer_id}  ",
        f"**Run ID:** {run_id}  ",
        f"",
        f"## Risk Assessment",
        f"- **Risk Tier:** {phase2.get('risk_tier', 'N/A')}",
        f"- **Complexity:** {phase2.get('implementation_complexity', 'N/A')}",
        f"- **Go-Live Urgency:** {phase2.get('go_live_urgency', 'N/A')}",
        f"- **Customer Type:** {phase2.get('customer_type', 'N/A')}",
        f"",
        f"## Overview",
        f"{phase1.get('overview', '')}",
        f"",
        f"## Sales Context",
        f"{phase3.get('summary', phase3.get('human_context', '')[:400])}",
    ])


def _build_completion_summary(run_id: str, customer_id: str, customer_name: str,
                               phases_completed: int, total_latency_ms: int,
                               phase_results: dict, download_url: str) -> dict:
    phases_done = len([k for k in phase_results if k != "error"])
    p8 = phase_results.get("phase8", {})
    final_status = "completed_with_gaps" if phase_results.get("phase6", {}).get("gaps_blocking") else "completed"
    return {
        "run_id":              run_id,
        "customer_id":         customer_id,
        "customer_name":       customer_name,
        "phases_completed":    phases_completed,
        "phases_done":         phases_done,
        "total_latency_ms":    total_latency_ms,
        "report_download_url": download_url,
        "phase_results":       phase_results,
        "status":              final_status,
        "wiki_page_path":      p8.get("wiki_page_path", ""),
        "wiki_indexed":        p8.get("wiki_indexed", False),
    }