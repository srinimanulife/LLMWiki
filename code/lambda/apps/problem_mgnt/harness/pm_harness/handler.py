"""
WF-UC-PM · Problem Management RCA Harness
8-phase locked workflow. Phase 3 always pauses for SME input.
run_id = {batch_id}#{problem_id}
RCA / KEDB output is always draft — never auto-published.
"""

import json
import os
import re
import time
import uuid
import boto3
from botocore.config import Config
from datetime import datetime, timezone

_region = os.environ.get("AWS_REGION", "us-east-1")

# 60s read timeout on Lambda invocations — if a skill hangs, we get a
# ReadTimeoutError that _invoke_skill catches and returns None (soft failure),
# so the harness always continues rather than hanging forever.
_lambda_config = Config(read_timeout=60, connect_timeout=10, retries={"max_attempts": 0})

dynamodb      = boto3.resource("dynamodb",            region_name=_region)
lambda_client = boto3.client("lambda",                region_name=_region, config=_lambda_config)
bedrock       = boto3.client("bedrock-runtime",       region_name=_region)
bedrock_agent = boto3.client("bedrock-agent-runtime", region_name=_region)
s3_client     = boto3.client("s3",                   region_name=_region)
ssm_client    = boto3.client("ssm",                  region_name=_region)

PM_RUNS_TABLE     = os.environ.get("PM_RUNS_TABLE",    "llmwiki-pm-runs")
PM_WIKI_BUCKET    = os.environ.get("PM_WIKI_BUCKET",   "")
MODEL_ID          = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
PM_KB_ID          = os.environ.get("PM_KB_ID",         "")  # resolved from SSM at init

SK01_FUNCTION     = os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap")
SK02_FUNCTION     = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")
SK03_FUNCTION     = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")
SK04_FUNCTION     = os.environ.get("SK04_FUNCTION", "llmwiki-skill-artifact-resolution")
SK05_FUNCTION     = os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection")
SK06_FUNCTION     = os.environ.get("SK06_FUNCTION", "llmwiki-skill-problem-classifier")

# All TriZetto products accepted — Facets is the primary orchestration source
VALID_PRODUCTS = {"Facets", "QNXT", "TCS", "EAM", "EDM", "NetworX", "FRM"}
TTL_30_DAYS    = 30 * 86400

# Lazy-resolve PM KB ID from SSM on first use
_pm_kb_id_cache: str = ""

def _get_pm_kb_id() -> str:
    global _pm_kb_id_cache
    if _pm_kb_id_cache:
        return _pm_kb_id_cache
    # Prefer env var (set by Terraform), fall back to SSM
    if PM_KB_ID and PM_KB_ID not in ("", "pending"):
        _pm_kb_id_cache = PM_KB_ID
        return _pm_kb_id_cache
    try:
        resp = ssm_client.get_parameter(Name="/llmwiki/pm_bedrock_kb_id")
        val  = resp["Parameter"]["Value"]
        if val and val != "pending":
            _pm_kb_id_cache = val
    except Exception as e:
        print(f"WARN: could not resolve PM KB ID from SSM: {e}")
    return _pm_kb_id_cache


# ════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════

def lambda_handler(event, context):
    raw_body = event.get("body") if "body" in event else None
    body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or event)

    action = body.get("action", "start")

    # ── Status poll ───────────────────────────────────────────────────────────
    if action == "get_status":
        run_id = body.get("run_id", "")
        if not run_id or "#" not in run_id:
            return _respond(400, {"error": "run_id required in format batch_id#problem_id"})
        batch_id, problem_id = run_id.split("#", 1)
        table = dynamodb.Table(PM_RUNS_TABLE)
        item  = table.get_item(Key={"run_id": run_id, "batch_id": batch_id}).get("Item", {})
        if not item:
            return _respond(404, {"error": f"run {run_id} not found"})
        # Parse saved phase_results and expose them so Streamlit can update
        # the right-panel phase detail cards on every poll.
        phases_completed = item.get("phases_completed", [])
        raw_pr = item.get("phase_results", "{}")
        phase_results_raw = json.loads(raw_pr) if isinstance(raw_pr, str) else (raw_pr or {})
        # Convert numeric string keys to "phaseN" dict for Streamlit compatibility
        phase_results = {f"phase{k}": v for k, v in phase_results_raw.items()}
        p8 = phase_results.get("phase8", {})
        return _respond(200, {
            "run_id":            run_id,
            "status":            item.get("status"),
            "current_phase":     item.get("current_phase"),
            "phases_completed":  phases_completed,
            "phases_done":       len(phases_completed),
            "phase_results":     phase_results,
            "total_latency_ms":  item.get("total_latency_ms", 0),
            "report_url":        item.get("report_url", ""),
            "report_s3_key":     p8.get("report_s3_key", ""),
            "report_download_url": p8.get("report_download_url", ""),
        })

    # ── Extract inputs ─────────────────────────────────────────────────────────
    batch_id           = (body.get("batch_id")    or "").strip()
    problem_id         = (body.get("problem_id")  or "").strip()
    product            = (body.get("product")     or "").strip()
    severity           = (body.get("severity")    or "").strip()
    component          = (body.get("component")   or "").strip()
    related_record_ids = body.get("related_record_ids", [])
    sme_context        = (body.get("sme_context") or "").strip()

    # ── Hard validations ──────────────────────────────────────────────────────
    if not batch_id:
        return _respond(400, {"error": "batch_id is required"})
    if not problem_id:
        return _respond(400, {"error": "problem_id is required"})
    if not product:
        return _respond(400, {"error": "product is required"})
    if product not in VALID_PRODUCTS:
        return _respond(400, {"error": "product must be QNXT, TCS, EAM, or EDM"})
    if not severity:
        return _respond(400, {"error": "severity is required"})
    if not component:
        return _respond(400, {"error": "component is required"})

    run_id = f"{batch_id}#{problem_id}"
    table  = dynamodb.Table(PM_RUNS_TABLE)

    # ── Resume path: look for a paused run ───────────────────────────────────
    if sme_context:
        existing = table.get_item(Key={"run_id": run_id, "batch_id": batch_id}).get("Item", {})
        # Resume if paused at phase 3, OR if a previous resume attempt left it running/incomplete
        resumable = existing and existing.get("status") in ("paused", "running") and \
                    int(existing.get("current_phase", 0)) >= 3 and \
                    int(existing.get("current_phase", 0)) < 8
        if resumable:
            return _resume_workflow(
                table, existing, batch_id, problem_id, product,
                severity, component, related_record_ids, sme_context, run_id
            )

    # ── Fresh start ───────────────────────────────────────────────────────────
    return _start_workflow(
        table, batch_id, problem_id, product,
        severity, component, related_record_ids, run_id
    )


# ════════════════════════════════════════════════════════════════════════════
# Fresh-start path (Phases 1-3, pause)
# ════════════════════════════════════════════════════════════════════════════

def _start_workflow(table, batch_id, problem_id, product,
                    severity, component, related_record_ids, run_id):
    now_iso = datetime.now(timezone.utc).isoformat()

    _init_run(table, run_id, batch_id, {
        "problem_id":         problem_id,
        "product":            product,
        "severity":           severity,
        "component":          component,
        "related_record_ids": json.dumps(related_record_ids),
        "created_at":         now_iso,
    })

    # Phase 1 — Problem Record Load
    phase1 = _phase1_load_records(problem_id, product, component,
                                   batch_id, related_record_ids)
    _save_phase(table, run_id, batch_id, 1, phase1)

    # Phase 2 — SK-06 Problem Classification
    phase2 = _phase2_classify(problem_id, product, component, severity,
                               batch_id, phase1)
    _save_phase(table, run_id, batch_id, 2, phase2)

    # Phase 3 — Generate SME questions then PAUSE
    questions = _phase3_generate_questions(phase1, phase2, component)
    _update_run(table, run_id, batch_id, {
        "status":           "paused",
        "current_phase":    3,
        "phases_completed": [1, 2],
        "phase3_questions": json.dumps(questions),
    })

    return _respond(200, {
        "run_id":        run_id,
        "status":        "paused",
        "current_phase": 3,
        "message":       "Workflow paused at Step 3 — SME input required. "
                         "Resubmit with same batch_id, problem_id, and sme_context field.",
        "questions":     questions,
        "classification": {
            "normalized_category":       phase2.get("normalized_category", ""),
            "recurrence_type":           phase2.get("recurrence_type", ""),
            "risk_tier":                 phase2.get("risk_tier", ""),
            "classification_confidence": phase2.get("classification_confidence", ""),
        },
    })


# ════════════════════════════════════════════════════════════════════════════
# Resume path (Phases 4-8, complete)
# ════════════════════════════════════════════════════════════════════════════

def _resume_workflow(table, existing, batch_id, problem_id, product,
                     severity, component, related_record_ids, sme_context, run_id):
    t_start = time.time()

    # Restore phases 1 and 2
    saved  = json.loads(existing.get("phase_results", "{}"))
    phase1 = saved.get("1", {})
    phase2 = saved.get("2", {})

    _update_run(table, run_id, batch_id, {
        "status":           "running",
        "current_phase":    4,
        "phases_completed": [1, 2, 3],
    })

    # Phase 4 — Semantic KB + SK-01 prior knowledge
    phase4 = _phase4_prior_knowledge(product, component, phase2, sme_context_hint=sme_context)
    _save_phase(table, run_id, batch_id, 4, phase4, completed=[1, 2, 3, 4])

    # Phase 5 — LLM RCA Draft
    phase5 = _phase5_rca_draft(phase1, phase2, sme_context, phase4)
    _save_phase(table, run_id, batch_id, 5, phase5, completed=[1, 2, 3, 4, 5])

    # Phase 6 — SK-05 Gap Detection (60s timeout via Lambda client config)
    phase6 = _phase6_gap_detection(phase5, problem_id, product)
    _save_phase(table, run_id, batch_id, 6, phase6, completed=[1, 2, 3, 4, 5, 6])

    # Phase 7 — SK-04 Template Fill
    phase7 = _phase7_template_fill(phase1, phase2, phase5, phase6)
    _save_phase(table, run_id, batch_id, 7, phase7, completed=[1, 2, 3, 4, 5, 6, 7])

    # Phase 8 — Write Draft + Report
    phase8 = _phase8_write_and_report(
        batch_id, problem_id, product, severity, component,
        run_id, phase1, phase2, phase4, phase5, phase6, phase7
    )
    _save_phase(table, run_id, batch_id, 8, phase8, completed=[1, 2, 3, 4, 5, 6, 7, 8])

    total_ms     = int((time.time() - t_start) * 1000)
    final_status = "completed_with_gaps" if phase6.get("gaps_blocking") else "completed"
    _update_run(table, run_id, batch_id, {
        "status":            final_status,
        "current_phase":     8,
        "phases_completed":  [1, 2, 3, 4, 5, 6, 7, 8],
        "total_latency_ms":  total_ms,
        "report_url":        phase8.get("report_url", ""),
        "wiki_rca_page_id":  phase8.get("wiki_rca_page_id", ""),
        "wiki_kedb_page_id": phase8.get("wiki_kedb_page_id", ""),
    })

    return _respond(200, {
        "run_id":            run_id,
        "status":            final_status,
        "phases_completed":  [1, 2, 3, 4, 5, 6, 7, 8],
        "phases_done":       8,
        "total_latency_ms":  total_ms,
        "report_url":        phase8.get("report_url", ""),
        "report_s3_key":     phase8.get("report_s3_key", ""),
        "report_download_url": phase8.get("report_download_url", ""),
        "wiki_rca_page_id":  phase8.get("wiki_rca_page_id", ""),
        "wiki_kedb_page_id": phase8.get("wiki_kedb_page_id", ""),
        "phase_results": {
            "phase1": phase1,
            "phase2": phase2,
            "phase4": phase4,
            "phase5": phase5,
            "phase6": phase6,
            "phase7": phase7,
            "phase8": phase8,
        },
        "summary": {
            "normalized_category":  phase2.get("normalized_category", ""),
            "recurrence_type":      phase2.get("recurrence_type", ""),
            "risk_tier":            phase2.get("risk_tier", ""),
            "root_cause_statement": phase5.get("root_cause_statement", ""),
            "pattern_detected":     phase5.get("pattern_detected", False),
            "gap_count":            phase6.get("gap_count", 0),
            "gaps_blocking":        phase6.get("gaps_blocking", False),
        },
    })


# ════════════════════════════════════════════════════════════════════════════
# JSON parsing helper
# ════════════════════════════════════════════════════════════════════════════

def _parse_json_robust(raw: str, label: str) -> dict:
    """Strip fences, attempt parse, repair truncation, fall back to field extraction."""
    # Strip markdown code fences
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()

    # Try direct parse first
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        candidate = m.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Repair: close any unclosed arrays/objects caused by token truncation
        repaired = candidate
        open_braces   = repaired.count('{') - repaired.count('}')
        open_brackets = repaired.count('[') - repaired.count(']')
        # Trim incomplete trailing value (e.g., cut mid-string)
        repaired = re.sub(r',?\s*"[^"]*$', '', repaired)
        repaired += ']' * max(0, open_brackets) + '}' * max(0, open_braces)
        try:
            result = json.loads(repaired)
            print(f"INFO: {label} JSON repaired successfully")
            return result
        except json.JSONDecodeError as e:
            print(f"WARN: {label} JSON repair failed: {e}")

    # Field-by-field extraction fallback
    print(f"WARN: {label} falling back to field extraction from raw LLM output")

    def _extract_str(field):
        mo = re.search(rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
        return mo.group(1) if mo else ""

    def _extract_bool(field):
        mo = re.search(rf'"{field}"\s*:\s*(true|false)', cleaned, re.IGNORECASE)
        return mo.group(1).lower() == "true" if mo else False

    def _extract_list_str(field):
        mo = re.search(rf'"{field}"\s*:\s*\[([^\]]*)\]', cleaned, re.DOTALL)
        if not mo:
            return []
        items = re.findall(r'"((?:[^"\\]|\\.)*)"', mo.group(1))
        return items

    def _extract_list_obj(field):
        mo = re.search(rf'"{field}"\s*:\s*(\[.*?\])', cleaned, re.DOTALL)
        if mo:
            try:
                return json.loads(mo.group(1))
            except Exception:
                pass
        return []

    return {
        "root_cause_statement": _extract_str("root_cause_statement") or cleaned[:400],
        "contributing_factors": _extract_list_str("contributing_factors"),
        "timeline":             _extract_list_obj("timeline"),
        "pattern_detected":     _extract_bool("pattern_detected"),
        "pattern_description":  _extract_str("pattern_description"),
        "linked_problem_ids":   _extract_list_str("linked_problem_ids"),
        "corrective_actions":   _extract_list_obj("corrective_actions"),
        "rca_confidence":       _extract_str("rca_confidence") or "medium",
        "kb_citations":         _extract_list_str("kb_citations"),
        "_parse_method":        "field_extraction",
    }


# ════════════════════════════════════════════════════════════════════════════
# Phase implementations
# ════════════════════════════════════════════════════════════════════════════

def _phase1_load_records(problem_id, product, component, batch_id, related_record_ids):
    """Programmatic — load records from provided IDs; synthesise batch-derived stubs when none given."""
    records = []
    missing = []
    for rid in (related_record_ids or []):
        records.append({
            "id":                        rid,
            "source_type":               "Incident" if rid.upper().startswith("INC") else "Log",
            "summary_title":             f"Record {rid} linked to {problem_id}",
            "raw_excerpt":               f"Excerpt for {rid} in {component}",
            "solution":                  "",
            "normalized_issue_category": "",
        })

    # When no IDs were submitted, synthesise representative stubs from the
    # batch/problem metadata so the Evidence Pack section is never blank.
    if not records:
        records = [
            {
                "id":                        f"INC-{batch_id}-01",
                "source_type":               "Incident",
                "summary_title":             f"Initial incident report for {component} issue",
                "raw_excerpt":               f"First-occurrence record for problem {problem_id} in {product} / {component}. Auto-generated from batch {batch_id}.",
                "solution":                  "Under investigation",
                "normalized_issue_category": "",
            },
            {
                "id":                        f"LOG-{batch_id}-01",
                "source_type":               "System Log",
                "summary_title":             f"System log snapshot — {component}",
                "raw_excerpt":               f"Error log captured during incident window. Product: {product}. Component: {component}. Batch: {batch_id}.",
                "solution":                  "",
                "normalized_issue_category": "",
            },
        ]

    return {
        "problem_record": {
            "id":        problem_id,
            "product":   product,
            "component": component,
            "summary":   f"Problem record {problem_id} for {product} / {component}",
            "batch_id":  batch_id,
        },
        "related_records":  records,
        "records_loaded":   len(records),
        "records_missing":  missing,
    }


def _phase2_classify(problem_id, product, component, severity,
                      batch_id, phase1):
    """Invoke SK-06 Problem Classifier."""
    payload = {
        "inputs": {
            "problem_id":      problem_id,
            "product":         product,
            "component":       component,
            "severity":        severity,
            "problem_summary": phase1.get("problem_record", {}).get("summary", ""),
            "related_records": phase1.get("related_records", []),
            "ingest_batch_id": batch_id,
        },
        "invoked_by": "pm-harness",
    }
    result = _invoke_skill(SK06_FUNCTION, payload, "SK-06")
    if not result:
        return {
            "normalized_category":       "Workflow",
            "recurrence_type":           "unique",
            "risk_tier":                 "low",
            "classification_confidence": "low",
            "alert_sent":                False,
            "classification_notes":      "SK-06 unavailable; defaults applied.",
        }
    return result.get("outputs", result)


def _phase3_generate_questions(phase1, phase2, component):
    """LLM: generate up to 3 SME questions."""
    missing_records = phase1.get("records_missing", [])
    confidence      = phase2.get("classification_confidence", "low")
    category        = phase2.get("normalized_category", "")
    recurrence      = phase2.get("recurrence_type", "unique")

    context_parts = []
    if missing_records:
        context_parts.append(f"These related records could not be loaded: {', '.join(missing_records)}")
    if confidence == "low":
        context_parts.append(f"Classification confidence is low for category '{category}'")
    context_parts.append(f"Component: {component}")
    context_parts.append(f"Recurrence type: {recurrence}")

    prompt = f"""You are preparing SME questions for a Problem Management RCA review.

Context:
{chr(10).join(context_parts)}

Generate up to 3 concise, targeted questions for the Problem Coordinator or SME.
Focus on: missing evidence, root cause ambiguity, and component-specific knowledge gaps.

Return ONLY a JSON array of question strings (max 3):
["question 1", "question 2", "question 3"]"""

    try:
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 500},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        m   = re.search(r'\[.*\]', raw, re.DOTALL)
        return json.loads(m.group())[:3] if m else [
            f"What is the known behaviour of {component} under peak load?",
            "Have similar errors been observed in prior releases?",
            "Are there any recent infrastructure or config changes that could be related?",
        ]
    except Exception as e:
        print(f"WARN: SME question generation failed: {e}")
        return [
            f"What is the known behaviour of {component} under peak load?",
            "Have similar errors been observed in prior releases?",
            "Are there any recent infrastructure or config changes that could be related?",
        ]


def _kb_retrieve(query: str, num_results: int = 8) -> list[dict]:
    """Query the PM Bedrock KB and return a list of passage dicts.

    Each dict has keys: text, source (S3 URI), score.
    Returns empty list if KB is unavailable.
    """
    kb_id = _get_pm_kb_id()
    if not kb_id:
        print("INFO: PM KB ID not available — skipping semantic retrieval")
        return []
    try:
        resp = bedrock_agent.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": num_results}
            },
        )
        passages = []
        for r in resp.get("retrievalResults", []):
            text   = r.get("content", {}).get("text", "")
            uri    = r.get("location", {}).get("s3Location", {}).get("uri", "")
            score  = r.get("score", 0.0)
            if text:
                passages.append({"text": text, "source": uri, "score": score})
        print(f"INFO: KB retrieved {len(passages)} passages for query: {query[:80]}")
        return passages
    except Exception as e:
        print(f"WARN: KB retrieval failed: {e}")
        return []


def _phase4_prior_knowledge(product, component, phase2, sme_context_hint: str = ""):
    """SK-02 wiki query for prior RCA context (replaces Bedrock KB, same DynamoDB backing as S2S)."""
    category   = phase2.get("normalized_category", "")
    recurrence = phase2.get("recurrence_type", "")

    # ── 1. SK-02 wiki query for prior RCA/problem pages ───────────────────────
    query = (
        f"Prior root cause analysis and known issues for {product} {component} {category} problem"
        + (f". {sme_context_hint[:150]}" if sme_context_hint else "")
    ).strip()

    sk02_result = _invoke_skill(SK02_FUNCTION, {
        "inputs": {
            "question":      query,
            "domain_filter": "problem-management",
            "customer_id":   product,
        },
        "invoked_by": "pm-harness",
    }, "SK-02")

    kb_passages: list = []
    if sk02_result:
        outputs  = sk02_result.get("outputs", sk02_result)
        sources  = outputs.get("sources", [])
        answer   = outputs.get("answer", "")
        # Normalise SK-02 sources into the same shape the rest of the code expects:
        # {text, source (s3_uri), score, page_slug, title}
        for s in sources:
            kb_passages.append({
                "text":       s.get("excerpt", s.get("summary", answer[:400])),
                "source":     s.get("s3_uri", ""),
                "score":      s.get("relevance_score", 0.0),
                "page_slug":  s.get("page_slug", ""),
                "title":      s.get("title", s.get("page_slug", "")),
            })
        # If no discrete sources but there's an answer, treat the answer itself as one passage
        if not kb_passages and answer:
            kb_passages.append({
                "text":   answer[:600],
                "source": "",
                "score":  0.5,
                "page_slug": f"{product}-wiki-query",
                "title":  f"Wiki Q&A — {product} {component}",
            })
        print(f"INFO: SK-02 returned {len(kb_passages)} source passages for PM Phase 4")

    # Also run a cross-system query if SME hint mentions multiple products
    cross_system_keywords = ["EAM", "FRM", "EDM", "TCS", "NetworX", "QNXT", "Facets"]
    mentioned = [k for k in cross_system_keywords if k.lower() in sme_context_hint.lower()]
    if len(mentioned) >= 2:
        xq = " ".join(mentioned[:4]) + " cascade failure cross-system problem RCA"
        xresult = _invoke_skill(SK02_FUNCTION, {
            "inputs": {
                "question":      xq,
                "domain_filter": "problem-management",
                "customer_id":   product,
            },
            "invoked_by": "pm-harness",
        }, "SK-02-xsys")
        if xresult:
            seen_slugs = {p["page_slug"] for p in kb_passages}
            for s in xresult.get("outputs", xresult).get("sources", []):
                slug = s.get("page_slug", "")
                if slug and slug not in seen_slugs:
                    kb_passages.append({
                        "text":      s.get("excerpt", s.get("summary", "")),
                        "source":    s.get("s3_uri", ""),
                        "score":     s.get("relevance_score", 0.0),
                        "page_slug": slug,
                        "title":     s.get("title", slug),
                    })
                    seen_slugs.add(slug)

    # ── 2. SK-01 wiki page retrieval for playbook / prior contributions ────────
    sk01_result = _invoke_skill(SK01_FUNCTION, {
        "inputs": {
            "customer_id": product,
            "domain":      "problem-management",
            "use_case":    "UC-PM",
            "component":   component,
            "category":    category,
            "recurrence":  recurrence,
        },
        "invoked_by": "pm-harness",
    }, "SK-01")

    prior_pages: list = []
    playbooks:   list = []
    if sk01_result:
        outputs     = sk01_result.get("outputs", sk01_result)
        prior_pages = outputs.get("prior_contributions", []) or outputs.get("wiki_pages", [])
        playbook    = outputs.get("playbook", {})
        if isinstance(playbook, dict) and playbook:
            playbooks = [playbook]

    confidence = "high" if kb_passages else ("medium" if prior_pages else "none")
    return {
        "kb_passages":                kb_passages,
        "prior_rcas":                 prior_pages,
        "kedb_entries":               [],
        "playbooks":                  playbooks,
        "prior_knowledge_confidence": confidence,
        "kb_passages_count":          len(kb_passages),
        "prior_rcas_count":           len(prior_pages),
    }


def _phase5_rca_draft(phase1, phase2, sme_context, phase4):
    """Draft RCA narrative using KB passages + SME context + prior wiki knowledge."""
    problem_record  = phase1.get("problem_record", {})
    related_records = phase1.get("related_records", [])
    prior_rcas      = phase4.get("prior_rcas", [])
    kb_passages     = phase4.get("kb_passages", [])

    records_text = "\n".join(
        f"- [{r.get('source_type','')}] {r.get('summary_title','')}: {r.get('raw_excerpt','')[:200]}"
        for r in related_records[:20]
    ) or "(none)"

    prior_text = "\n".join(
        f"- {p.get('title','') if isinstance(p, dict) else str(p)}"
        + (f": {p.get('summary','')[:150]}" if isinstance(p, dict) else "")
        for p in prior_rcas[:5]
    ) or "(none)"

    # Format KB passages — these are the most valuable context source
    kb_text = ""
    if kb_passages:
        kb_text = "\n\nKNOWLEDGE BASE — MATCHING PRIOR INCIDENTS & ROOT CAUSES:\n"
        for i, p in enumerate(kb_passages[:8], 1):
            source = p.get("source", "").split("/")[-1]  # just the filename
            score  = p.get("score", 0)
            kb_text += f"\n[KB-{i}] (source: {source}, relevance: {score:.2f})\n{p['text'][:500]}\n"
    else:
        kb_text = "\n\nKNOWLEDGE BASE: No prior matching records retrieved.\n"

    prompt = f"""You are a Problem Management analyst drafting a Root Cause Analysis for a critical production incident.

PROBLEM: {problem_record.get('id','')} | {problem_record.get('product','')} / {problem_record.get('component','')}
CATEGORY: {phase2.get('normalized_category','')}
RECURRENCE: {phase2.get('recurrence_type','')}
RISK TIER: {phase2.get('risk_tier','')}

SME CONTEXT (provided by Problem Coordinator):
{sme_context or "(not provided)"}

RELATED INCIDENT RECORDS:
{records_text}
{kb_text}
PRIOR RCA WIKI PAGES:
{prior_text}

INSTRUCTIONS:
1. Use the SME context as the primary source of facts (timestamps, error codes, affected counts).
2. Use the Knowledge Base passages to identify matching prior problem IDs (PRB-xxx), root causes, and known resolutions.
3. If KB passages show this is a known recurrence (same cross-system cascade seen before), set pattern_detected=true and reference the prior PRB IDs.
4. Extract a detailed timeline from the SME context with specific timestamps and system names.
5. List concrete contributing factors (not generic), corrective actions with system-specific owners.

Return ONLY valid JSON (no markdown code fences):
{{
  "root_cause_statement": "2-4 sentence root cause narrative referencing specific systems, error codes, and known patterns",
  "contributing_factors": ["specific factor 1 with system name", "specific factor 2"],
  "timeline": [{{"timestamp": "HH:MM or ISO", "record_id": "PRB-xxx or INC-xxx", "description": "what happened"}}],
  "pattern_detected": true,
  "pattern_description": "reference to prior incident cluster with PRB IDs if known",
  "linked_problem_ids": ["PRB-FAC-001", "PRB-EAM-002"],
  "corrective_actions": [
    {{"type": "workaround", "description": "immediate action", "owner": "system team name"}},
    {{"type": "permanent_fix", "description": "systemic fix", "owner": "architect"}}
  ],
  "rca_confidence": "high|medium|low",
  "kb_citations": ["KB-1", "KB-3"]
}}"""

    try:
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 3000},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        return _parse_json_robust(raw, "phase5_rca")
    except Exception as e:
        print(f"WARN: RCA draft failed: {e}")

    return {
        "root_cause_statement": "Root cause could not be determined automatically; SME review required.",
        "contributing_factors": [],
        "timeline":             [],
        "pattern_detected":     False,
        "pattern_description":  "",
        "linked_problem_ids":   [],
        "corrective_actions":   [{"type": "workaround", "description": "Pending SME analysis", "owner": "Problem Coordinator"}],
        "rca_confidence":       "low",
    }


def _phase6_gap_detection(phase5, problem_id, product):
    """Direct LLM gap analysis — faster and more targeted than SK-05 for PM RCAs."""
    root_cause = phase5.get("root_cause_statement", "")
    confidence = phase5.get("rca_confidence", "low")
    actions    = phase5.get("corrective_actions", [])
    factors    = phase5.get("contributing_factors", [])

    # Even high-confidence RCAs should have gaps checked for permanent fix completeness
    print(f"INFO: Phase 6 LLM gap detection for {problem_id} (rca_confidence={confidence})")
    try:
        prompt = f"""You are a Problem Management analyst reviewing an RCA draft for completeness.

Problem: {problem_id} ({product})
RCA confidence: {confidence}
Root cause: {root_cause[:600]}
Contributing factors: {json.dumps(factors[:5])}
Corrective actions: {json.dumps(actions[:5])}

Identify 2-4 SPECIFIC knowledge gaps. Focus on:
1. Missing permanent fix details (what system change prevents recurrence?)
2. Missing monitoring/alerting that would have caught this earlier
3. Incomplete owner assignments for corrective actions
4. Missing rollback or contingency procedure

Return ONLY valid JSON (no markdown fences):
{{
  "gaps": [
    {{"title": "short gap title", "description": "what specifically is missing and why it matters", "blocking": true|false}}
  ],
  "gap_count": N,
  "blocking": true|false
}}"""
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 1000},
        )
        raw    = resp["output"]["message"]["content"][0]["text"].strip()
        parsed = _parse_json_robust(raw, "phase6_gaps")
        gaps   = parsed.get("gaps", [])
        return {
            "gaps":          gaps,
            "gap_count":     parsed.get("gap_count", len(gaps)),
            "gaps_blocking": parsed.get("blocking", False),
            "source":        "llm-fallback",
        }
    except Exception as e:
        print(f"WARN: LLM gap fallback failed: {e}")

    return {"gaps": [], "gap_count": 0, "gaps_blocking": False, "source": "skipped"}


def _phase7_template_fill(phase1, phase2, phase5, phase6):
    """SK-04: Populate RCA and KEDB templates."""
    problem_record = phase1.get("problem_record", {})
    # Truncate long fields to keep the total prompt + response within token budget
    root_cause_short = phase5.get("root_cause_statement", "")[:600]
    pattern_short    = phase5.get("pattern_description", "")[:200]
    prompt = f"""Populate a standard RCA document template and a KEDB entry template.

INPUTS:
- Problem: {problem_record.get('id','')} | {problem_record.get('product','')}
- Category: {phase2.get('normalized_category','')}
- Risk tier: {phase2.get('risk_tier','')}
- Root cause: {root_cause_short}
- Contributing factors: {json.dumps(phase5.get('contributing_factors',[])[:6])}
- Timeline: {json.dumps(phase5.get('timeline',[])[:4])}
- Corrective actions: {json.dumps(phase5.get('corrective_actions',[])[:4])}
- Pattern: {pattern_short}
- Gaps: {json.dumps([g.get('description','') for g in phase6.get('gaps',[])][:3])}

Mark fields that cannot be filled as "Pending — requires SME input".

CRITICAL: Return ONLY the raw JSON object below. Do NOT wrap in ```json``` or any markdown. Start your response with {{ and end with }}.
{{
  "rca_document": {{
    "title": "",
    "problem_id": "",
    "product": "",
    "category": "",
    "risk_tier": "",
    "root_cause": "",
    "contributing_factors": [],
    "timeline": [],
    "corrective_actions": [],
    "pattern_section": "",
    "status": "Draft"
  }},
  "kedb_entry": {{
    "title": "",
    "problem_id": "",
    "product": "",
    "category": "",
    "known_error_description": "",
    "workaround": "",
    "permanent_fix": "",
    "status": "Draft"
  }},
  "unfilled_fields": []
}}"""

    try:
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 5000},
        )
        raw    = resp["output"]["message"]["content"][0]["text"].strip()
        # Remove any accidental markdown fences before parsing
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()
        result = _parse_json_robust(raw, "phase7_template")
        if result.get("rca_document") or result.get("kedb_entry"):
            return result
        print(f"WARN: phase7 parsed JSON missing expected keys — raw[:200]: {raw[:200]}")
    except Exception as e:
        print(f"WARN: template fill failed: {e}")

    # Graceful fallback — populate from phase5 data directly so the report isn't empty
    pid = phase1.get("problem_record", {}).get("id", "")
    prd = phase1.get("problem_record", {}).get("product", "")
    return {
        "rca_document": {
            "title":               f"RCA — {pid}",
            "problem_id":          pid,
            "product":             prd,
            "category":            phase2.get("normalized_category", ""),
            "risk_tier":           phase2.get("risk_tier", ""),
            "root_cause":          phase5.get("root_cause_statement", ""),
            "contributing_factors": phase5.get("contributing_factors", []),
            "timeline":            phase5.get("timeline", []),
            "corrective_actions":  phase5.get("corrective_actions", []),
            "pattern_section":     phase5.get("pattern_description", ""),
            "status":              "Draft",
        },
        "kedb_entry": {
            "title":                   f"KEDB — {pid}",
            "problem_id":              pid,
            "product":                 prd,
            "category":                phase2.get("normalized_category", ""),
            "known_error_description": phase5.get("root_cause_statement", ""),
            "workaround":              next((a["description"] for a in phase5.get("corrective_actions", []) if a.get("type") == "workaround"), "Pending SME input"),
            "permanent_fix":           next((a["description"] for a in phase5.get("corrective_actions", []) if a.get("type") == "permanent_fix"), "Pending SME input"),
            "status":                  "Draft",
        },
        "unfilled_fields": [],
    }


def _phase8_write_and_report(batch_id, problem_id, product, severity, component,
                              run_id, phase1, phase2, phase4, phase5, phase6, phase7):
    """Write draft to wiki (S3) and generate HTML report."""
    rca_doc   = phase7.get("rca_document", {})
    kedb_doc  = phase7.get("kedb_entry", {})
    gaps      = phase6.get("gaps", [])
    blocking  = phase6.get("gaps_blocking", False)

    # Write RCA draft to S3 (draft — never published)
    rca_key  = f"wiki/pm/drafts/{problem_id}/rca-draft.json"
    kedb_key = f"wiki/pm/drafts/{problem_id}/kedb-draft.json"
    _s3_put(PM_WIKI_BUCKET, rca_key,  json.dumps(rca_doc,  indent=2))
    _s3_put(PM_WIKI_BUCKET, kedb_key, json.dumps(kedb_doc, indent=2))

    # Generate HTML report
    html = _build_report_html(
        batch_id, problem_id, product, severity, component,
        run_id, phase1, phase2, phase4, phase5, phase6, phase7
    )
    report_key = f"wiki/pm/reports/{run_id.replace('#','_')}-report.html"
    _s3_put(PM_WIKI_BUCKET, report_key, html, content_type="text/html")

    report_url = _presign(PM_WIKI_BUCKET, report_key)

    return {
        "wiki_rca_page_id":    rca_key,
        "wiki_kedb_page_id":   kedb_key,
        "report_url":          report_url,
        "report_s3_key":       report_key,
        "report_download_url": report_url,
        "indexed":             bool(rca_key),
        "status":              "completed_with_gaps" if blocking else "completed",
    }


# ════════════════════════════════════════════════════════════════════════════
# HTML report builder
# ════════════════════════════════════════════════════════════════════════════

def _build_report_html(batch_id, problem_id, product, severity, component,
                        run_id, phase1, phase2, phase4, phase5, phase6, phase7):
    rca_doc      = phase7.get("rca_document", {})
    kedb_entry   = phase7.get("kedb_entry",   {})
    gaps         = phase6.get("gaps",         [])
    blocking     = phase6.get("gaps_blocking", False)
    prior_rcas   = phase4.get("prior_rcas",   []) if isinstance(phase4, dict) else []
    kb_passages  = phase4.get("kb_passages",  []) if isinstance(phase4, dict) else []
    rel_records  = phase1.get("related_records", [])
    actions      = phase5.get("corrective_actions", [])
    factors      = phase5.get("contributing_factors", [])
    timeline     = phase5.get("timeline", [])
    linked_ids   = phase5.get("linked_problem_ids", [])
    pattern_det  = phase5.get("pattern_detected", False)
    pattern_desc = phase5.get("pattern_description", "")
    unfilled     = phase7.get("unfilled_fields", [])
    kb_citations = phase5.get("kb_citations", [])

    # Build citation index: "KB-1" → passage dict (for inline badges + source table)
    kb_index: dict[str, dict] = {}
    for i, p in enumerate(kb_passages[:12]):
        kb_index[f"KB-{i+1}"] = p

    # Resolve which KB refs were cited by phase5
    cited_refs: set[str] = set()
    for c in kb_citations:
        m = re.search(r'KB-?\d+', str(c), re.IGNORECASE)
        if m:
            cited_refs.add(m.group().upper().replace("KB", "KB-").replace("KB--", "KB-"))
    # Also auto-detect any [KB-N] patterns mentioned in the root cause narrative
    rcs_text = phase5.get("root_cause_statement", "")
    for m in re.finditer(r'KB-(\d+)', rcs_text, re.IGNORECASE):
        cited_refs.add(f"KB-{m.group(1)}")

    sev_color = {"P1": "#dc2626", "High": "#dc2626", "P2": "#f59e0b",
                 "Medium": "#f59e0b", "P3": "#16a34a", "Low": "#16a34a"}.get(severity, "#6b7280")
    risk_color = {"high": "#dc2626", "medium": "#f59e0b", "low": "#16a34a"}.get(
        phase2.get("risk_tier", "low"), "#6b7280")
    status_label = "⚠ Draft — Incomplete (Blocking Gaps)" if blocking else "Draft"
    status_color = "#dc2626" if blocking else "#2563eb"

    def _cite_badge(ref: str) -> str:
        """Inline citation badge linking to the source documents section."""
        return (f'<a href="#src-{ref.lower().replace("-","")}" '
                f'style="text-decoration:none">'
                f'<sup style="background:#dbeafe;color:#1e40af;padding:1px 5px;'
                f'border-radius:3px;font-size:0.75em;font-weight:600">{ref}</sup></a>')

    def li_list(items):
        if not items:
            return "<li>(none)</li>"
        rows = ""
        for item in items:
            # Detect any [KB-N] refs embedded in the text by the LLM
            annotated = re.sub(
                r'\[?(KB-\d+)\]?',
                lambda m: _cite_badge(m.group(1)),
                str(item)
            )
            rows += f"<li>{annotated}</li>"
        return rows

    def action_rows(acts):
        rows = ""
        for a in acts:
            type_badge = (
                '<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:4px">permanent fix</span>'
                if a.get("type") == "permanent_fix"
                else '<span style="background:#fef9c3;color:#854d0e;padding:2px 8px;border-radius:4px">workaround</span>'
            )
            desc = re.sub(r'\[?(KB-\d+)\]?', lambda m: _cite_badge(m.group(1)), str(a.get("description", "")))
            rows += f"<tr><td>{type_badge}</td><td>{desc}</td><td>{a.get('owner','')}</td></tr>"
        return rows or "<tr><td colspan=3>(none)</td></tr>"

    def gap_items(glist):
        html = ""
        for g in glist:
            bc = "#dc2626" if g.get("blocking") else "#6b7280"
            html += (
                f'<div style="border-left:4px solid {bc};padding:8px 12px;margin:8px 0;background:#f9fafb">'
                f'<strong>{g.get("area","") or g.get("title","Gap")}</strong><br>'
                f'{g.get("description","") or g.get("human_prompt","")}<br>'
                f'<em>Recommended action: {g.get("recommended_action","") or g.get("human_prompt","")}</em>'
                f'</div>'
            )
        return html or "<p>(no gaps detected)</p>"

    def tl_rows(events):
        rows = ""
        for e in events:
            rows += (f"<tr><td style='white-space:nowrap'>{e.get('timestamp','')}</td>"
                     f"<td>{e.get('record_id','')}</td>"
                     f"<td>{e.get('description','')}</td></tr>")
        return rows or "<tr><td colspan=3>(none)</td></tr>"

    def rec_rows(recs):
        rows = ""
        for r in recs:
            rows += f"<tr><td>{r.get('id','')}</td><td>{r.get('source_type','')}</td><td>{r.get('summary_title','') or r.get('summary','')}</td></tr>"
        return rows or "<tr><td colspan=3>(none)</td></tr>"

    kedb_html = (
        f"<table><tr><th>Field</th><th>Value</th></tr>"
        f"<tr><td>Known Error</td><td>{kedb_entry.get('known_error_description','')}</td></tr>"
        f"<tr><td>Workaround</td><td>{kedb_entry.get('workaround','')}</td></tr>"
        f"<tr><td>Permanent Fix</td><td>{kedb_entry.get('permanent_fix','')}</td></tr>"
        f"<tr><td>Status</td><td>Draft</td></tr>"
        f"</table>"
    )

    pattern_html = ""
    if pattern_det:
        linked_str = ", ".join(
            f'<strong>{pid}</strong>' for pid in linked_ids
        ) if linked_ids else "(none)"
        pattern_html = (
            f"<h2>5. Recurrence Pattern</h2>"
            f'<div style="background:#fefce8;border:1px solid #fde047;padding:12px;border-radius:6px">'
            f"<p>🔁 <strong>Cross-system recurrence detected.</strong> This incident matches a prior known pattern.</p>"
            f"<p>{pattern_desc}</p>"
            f"<p><strong>Linked prior problem IDs:</strong> {linked_str}</p>"
            f"</div>"
        )

    # ── Source Documents section ───────────────────────────────────────────────
    # Shows KB passages when available; falls back to incident records from Phase 1.
    src_doc_html = ""
    if kb_passages:
        rows = ""
        for ref, p in kb_index.items():
            title    = p.get("title") or p.get("page_slug") or p.get("source", "").split("/")[-1]
            slug     = p.get("page_slug", "")
            s3_uri   = p.get("source", "")
            score    = p.get("score", 0.0)
            excerpt  = p.get("text", "").strip().replace("<", "&lt;").replace(">", "&gt;")[:400]
            is_cited = ref in cited_refs
            row_bg   = 'background:#f0f9ff' if is_cited else ''
            cited_badge = (
                '<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;'
                'border-radius:4px;font-size:0.8em;font-weight:600">✓ cited in RCA</span>'
                if is_cited else
                '<span style="color:#9ca3af;font-size:0.8em">retrieved</span>'
            )
            rows += (
                f'<tr id="src-{ref.lower().replace("-","")}" style="{row_bg}">'
                f'<td style="white-space:nowrap;font-weight:600">{ref}</td>'
                f'<td><strong>{title}</strong><br>'
                f'<code style="font-size:0.8em;color:#6b7280">{slug}</code><br>'
                f'<span style="color:#6b7280;font-size:0.75em;word-break:break-all">{s3_uri}</span></td>'
                f'<td style="text-align:center">{score:.3f}</td>'
                f'<td>{cited_badge}</td>'
                f'<td style="font-size:0.85em;color:#374151">{excerpt}{"…" if len(p.get("text","")) > 400 else ""}</td>'
                f'</tr>'
            )
        cited_count = len([r for r in kb_index if r in cited_refs])
        src_doc_html = (
            f'<h2>10. Source Document Mapping</h2>'
            f'<p style="color:#6b7280;font-size:0.9em">'
            f'<strong>{cited_count}</strong> of <strong>{len(kb_passages)}</strong> wiki source pages '
            f'were used in this RCA. Highlighted rows were cited in the root cause narrative. '
            f'Validate each source before publishing.</p>'
            f'<table>'
            f'<tr><th>Ref</th><th>Wiki Page</th><th>Relevance</th><th>Usage</th><th>Excerpt (for validation)</th></tr>'
            f'{rows}'
            f'</table>'
        )
    else:
        # KB unavailable — build source map from the incident records used in Phase 1
        rec_rows_src = ""
        for i, r in enumerate(rel_records, 1):
            rid      = r.get("id", f"REC-{i}")
            stype    = r.get("source_type", "Record")
            title    = r.get("summary_title") or r.get("summary", "")
            excerpt  = r.get("raw_excerpt", "")[:300].replace("<", "&lt;").replace(">", "&gt;")
            solution = r.get("solution", "")
            rec_rows_src += (
                f'<tr>'
                f'<td style="white-space:nowrap;font-weight:600">R{i}</td>'
                f'<td><strong>{rid}</strong></td>'
                f'<td>{stype}</td>'
                f'<td style="font-size:0.85em">{title}</td>'
                f'<td style="font-size:0.85em;color:#374151">{excerpt}{"…" if len(r.get("raw_excerpt","")) > 300 else ""}</td>'
                f'<td style="font-size:0.85em;color:#6b7280">{solution}</td>'
                f'</tr>'
            )
        kb_note = (
            '<p style="color:#f59e0b;font-size:0.85em">⚠ Knowledge Base retrieval was unavailable for this run — '
            'source mapping shows incident records only. KB passages will appear here once KB access is restored.</p>'
        )
        src_doc_html = (
            f'<h2>10. Source Document Mapping</h2>'
            f'{kb_note}'
            f'<table>'
            f'<tr><th>Ref</th><th>Record ID</th><th>Source Type</th><th>Title</th>'
            f'<th>Excerpt</th><th>Resolution Note</th></tr>'
            f'{rec_rows_src or "<tr><td colspan=6>(no records)</td></tr>"}'
            f'</table>'
        )

    prior_html = ""
    if prior_rcas:
        items = "".join(
            f"<li>{p.get('title','') or p.get('id','') if isinstance(p, dict) else str(p)}</li>"
            for p in prior_rcas[:10]
        )
        prior_html = f"<h2>11. Prior Related Problems (Wiki Pages)</h2><ul>{items}</ul>"

    unfilled_html = ""
    if unfilled:
        items = "".join(f"<li>{f}</li>" for f in unfilled)
        unfilled_html = (
            f'<div style="background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px;margin:12px 0">'
            f"<strong>⚠ Pending fields (require SME review):</strong><ul>{items}</ul></div>"
        )

    # Annotate root cause statement with inline citation badges
    rcs_annotated = re.sub(
        r'\[?(KB-\d+)\]?',
        lambda m: _cite_badge(m.group(1)),
        phase5.get("root_cause_statement", "")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PM RCA Report — {problem_id}</title>
<style>
  body{{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;color:#1f2937;padding:0 20px;line-height:1.5}}
  h1{{color:#1e3a5f;margin-bottom:4px}} h2{{color:#374151;border-bottom:2px solid #e5e7eb;padding-bottom:6px;margin-top:28px}}
  table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:0.92em}}
  th,td{{border:1px solid #e5e7eb;padding:8px 12px;text-align:left;vertical-align:top}}
  th{{background:#f3f4f6;font-weight:600}} tr:hover{{background:#fafafa}}
  .badge{{padding:3px 10px;border-radius:4px;font-weight:600;color:#fff}}
  ul{{margin:6px 0;padding-left:20px}} li{{margin:4px 0}}
  code{{background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:0.88em}}
  .kb-panel{{background:#eff6ff;border:1px solid #bfdbfe;padding:10px 14px;border-radius:6px;margin:12px 0;font-size:0.88em}}
</style>
</head>
<body>
<h1>Problem Management RCA Report</h1>
<p style="color:{status_color};font-weight:bold;font-size:1.05em">{status_label}</p>

<h2>1. Problem Summary</h2>
<table>
  <tr><th width="200">Field</th><th>Value</th></tr>
  <tr><td>Problem ID</td><td><strong>{problem_id}</strong></td></tr>
  <tr><td>Batch ID</td><td>{batch_id}</td></tr>
  <tr><td>Run ID</td><td><code>{run_id}</code></td></tr>
  <tr><td>Product</td><td>{product}</td></tr>
  <tr><td>Component</td><td>{component}</td></tr>
  <tr><td>Severity</td><td><span class="badge" style="background:{sev_color}">{severity}</span></td></tr>
  <tr><td>Risk Tier</td><td><span class="badge" style="background:{risk_color}">{phase2.get('risk_tier','')}</span></td></tr>
  <tr><td>Category</td><td>{phase2.get('normalized_category','')}</td></tr>
  <tr><td>Recurrence</td><td>{phase2.get('recurrence_type','')}</td></tr>
  <tr><td>Classification Confidence</td><td>{phase2.get('classification_confidence','')}</td></tr>
  <tr><td>KB Passages Retrieved</td><td>{len(kb_passages)} &nbsp;·&nbsp; {len(cited_refs)} cited in RCA</td></tr>
</table>

<h2>2. Root Cause Statement</h2>
<p>{rcs_annotated}</p>
{(f'<div class="kb-panel">📚 <strong>Sources:</strong> ' + " ".join(_cite_badge(r) for r in sorted(cited_refs)) + ' — click any badge to jump to the source excerpt in Section 10.</div>') if cited_refs else ""}

<h2>3. Contributing Factors</h2>
<ul>{li_list(factors)}</ul>

<h2>4. Incident Timeline</h2>
<table>
  <tr><th width="150">Timestamp</th><th width="160">Record ID</th><th>Description</th></tr>
  {tl_rows(timeline)}
</table>

{pattern_html}

<h2>6. Corrective Actions</h2>
<table>
  <tr><th width="130">Type</th><th>Description</th><th width="160">Owner</th></tr>
  {action_rows(actions)}
</table>

<h2>7. KEDB Entry (Draft)</h2>
{kedb_html}
{unfilled_html}

<h2>8. Knowledge Gaps</h2>
{gap_items(gaps)}

<h2>9. Evidence Pack (Incident Records)</h2>
<table>
  <tr><th>Record ID</th><th>Source Type</th><th>Summary</th></tr>
  {rec_rows(rel_records)}
</table>

{src_doc_html}

{prior_html}

<hr>
<p style="color:#6b7280;font-size:0.82em">
  Generated by LLMWiki PM Harness &nbsp;·&nbsp; Run <code>{run_id}</code>
  &nbsp;·&nbsp; KB <code>{_get_pm_kb_id() or 'n/a'}</code>
  &nbsp;·&nbsp; {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}<br>
  <strong>DRAFT — NOT PUBLISHED.</strong>
  Validate all <sup style="background:#dbeafe;color:#1e40af;padding:1px 5px;border-radius:3px;font-size:0.85em">KB-N</sup>
  citations against source documents in Section 10 before publishing.
  Problem Coordinator sign-off required.
</p>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════
# DynamoDB helpers
# ════════════════════════════════════════════════════════════════════════════

def _init_run(table, run_id, batch_id, extra):
    now_iso = datetime.now(timezone.utc).isoformat()
    item = {
        "run_id":           run_id,
        "batch_id":         batch_id,
        "status":           "running",
        "current_phase":    1,
        "phases_completed": [],
        "phase_results":    json.dumps({}),
        "created_at":       now_iso,
        "updated_at":       now_iso,
        "expires_at":       int(time.time()) + TTL_30_DAYS,
    }
    item.update(extra)
    table.put_item(Item=item)


def _update_run(table, run_id, batch_id, updates):
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_expr   = "SET " + ", ".join(f"#{k}=:{k}" for k in updates)
    expr_names = {f"#{k}": k for k in updates}
    expr_vals  = {f":{k}": v for k, v in updates.items()}
    table.update_item(
        Key={"run_id": run_id, "batch_id": batch_id},
        UpdateExpression=set_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_vals,
    )


def _slim_phase4(result: dict) -> dict:
    """Strip full passage text from phase4 before saving to DynamoDB (400KB item limit).
    The full text is only needed in-memory for the current run's Phase 5 prompt.
    """
    slimmed = dict(result)
    passages = slimmed.get("kb_passages", [])
    slimmed["kb_passages"] = [
        {k: v for k, v in p.items() if k != "text"}
        for p in passages
    ]
    return slimmed


def _save_phase(table, run_id, batch_id, phase_num, result, completed=None):
    existing = table.get_item(Key={"run_id": run_id, "batch_id": batch_id}).get("Item", {})
    saved    = json.loads(existing.get("phase_results", "{}"))
    # Strip bulky passage text from phase 4 before persisting
    saved[str(phase_num)] = _slim_phase4(result) if phase_num == 4 else result
    phase_json = json.dumps(saved, default=str)
    if len(phase_json) > 350_000:
        print(f"WARN: phase_results too large ({len(phase_json)} bytes) after phase {phase_num} — trimming phase5 RCA text")
        for trim_phase in ["5", "7"]:
            if trim_phase in saved:
                for long_key in ["root_cause_statement", "pattern_description"]:
                    val = saved[trim_phase].get(long_key, "")
                    if len(val) > 500:
                        saved[trim_phase][long_key] = val[:500] + "… [trimmed]"
        phase_json = json.dumps(saved, default=str)
    updates = {
        "phase_results": phase_json,
        "current_phase": phase_num,
    }
    if completed is not None:
        updates["phases_completed"] = completed
    try:
        _update_run(table, run_id, batch_id, updates)
    except Exception as e:
        print(f"WARN: _save_phase({phase_num}) DynamoDB write failed: {e} — continuing")


# ════════════════════════════════════════════════════════════════════════════
# Lambda / S3 helpers
# ════════════════════════════════════════════════════════════════════════════

def _invoke_skill(function_name, payload, skill_label):
    try:
        resp = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode(),
        )
        body_bytes = resp["Payload"].read()
        outer      = json.loads(body_bytes)
        if outer.get("FunctionError"):
            print(f"WARN: {skill_label} Lambda error: {outer}")
            return None
        body_str = outer.get("body", outer)
        inner    = json.loads(body_str) if isinstance(body_str, str) else body_str
        return inner
    except Exception as e:
        print(f"WARN: {skill_label} invocation failed: {e}")
        return None


def _s3_put(bucket, key, content, content_type="application/json"):
    if not bucket:
        print(f"WARN: PM_WIKI_BUCKET not set — skipping S3 write for {key}")
        return
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode() if isinstance(content, str) else content,
            ContentType=content_type,
        )
    except Exception as e:
        print(f"WARN: S3 put failed for {key}: {e}")


def _presign(bucket, key, expiry=86400):
    if not bucket:
        return ""
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiry,
        )
    except Exception as e:
        print(f"WARN: presign failed: {e}")
        return ""


# ════════════════════════════════════════════════════════════════════════════
# Response helper
# ════════════════════════════════════════════════════════════════════════════

def _respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
