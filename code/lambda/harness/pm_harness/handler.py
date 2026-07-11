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

dynamodb      = boto3.resource("dynamodb",       region_name=_region)
lambda_client = boto3.client("lambda",           region_name=_region)
bedrock       = boto3.client("bedrock-runtime",  region_name=_region)
s3_client     = boto3.client("s3",              region_name=_region, config=Config(signature_version="s3v4"))

PM_RUNS_TABLE     = os.environ.get("PM_RUNS_TABLE",    "llmwiki-pm-runs")
PM_WIKI_BUCKET    = os.environ.get("PM_WIKI_BUCKET",   "")
MODEL_ID          = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

SK01_FUNCTION     = os.environ.get("SK01_FUNCTION", "llmwiki-skill-context-bootstrap")
SK02_FUNCTION     = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")
SK03_FUNCTION     = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")
SK04_FUNCTION     = os.environ.get("SK04_FUNCTION", "llmwiki-skill-artifact-resolution")
SK05_FUNCTION     = os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection")
SK06_FUNCTION     = os.environ.get("SK06_FUNCTION", "llmwiki-skill-problem-classifier")

VALID_PRODUCTS = {"QNXT", "TCS", "EAM", "EDM", "Facets", "FACETS"}
TTL_30_DAYS    = 30 * 86400


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
        raw_pr        = item.get("phase_results", "{}")
        phase_results = json.loads(raw_pr) if isinstance(raw_pr, str) else (raw_pr or {})
        phases_done   = len([k for k in phase_results if k != "error"])
        p8            = phase_results.get("8", phase_results.get("phase8", {}))
        return _respond(200, {
            "run_id":               run_id,
            "status":               item.get("status"),
            "current_phase":        item.get("current_phase"),
            "phases_completed":     item.get("phases_completed", []),
            "phases_done":          phases_done,
            "phase_results":        {f"phase{k}": v for k, v in phase_results.items()},
            "report_download_url":  p8.get("report_download_url", item.get("report_download_url", item.get("report_url", ""))),
            "total_latency_ms":     item.get("total_latency_ms", 0),
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
        return _respond(400, {"error": "product must be QNXT, TCS, EAM, EDM, or Facets"})
    if not severity:
        return _respond(400, {"error": "severity is required"})
    if not component:
        return _respond(400, {"error": "component is required"})

    run_id = f"{batch_id}#{problem_id}"
    table  = dynamodb.Table(PM_RUNS_TABLE)

    # ── Resume path: look for a paused run ───────────────────────────────────
    if sme_context:
        existing = table.get_item(Key={"run_id": run_id, "batch_id": batch_id}).get("Item", {})
        if existing and existing.get("status") == "paused":
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
    saved = json.loads(existing.get("phase_results", "{}"))
    phase1 = saved.get("1", {})
    phase2 = saved.get("2", {})

    _update_run(table, run_id, batch_id, {"status": "running", "current_phase": 4})

    # Phase 4 — SK-01 Load Prior Knowledge
    phase4 = _phase4_prior_knowledge(product, component, phase2)
    _save_phase(table, run_id, batch_id, 4, phase4)

    # Phase 5 — SK-02 RCA Draft
    phase5 = _phase5_rca_draft(phase1, phase2, sme_context, phase4)
    _save_phase(table, run_id, batch_id, 5, phase5)

    # Phase 6 — SK-05 Gap Detection
    phase6 = _phase6_gap_detection(phase5, problem_id, product)
    _save_phase(table, run_id, batch_id, 6, phase6)

    # Phase 7 — SK-04 Template Fill
    phase7 = _phase7_template_fill(phase1, phase2, phase5, phase6)
    _save_phase(table, run_id, batch_id, 7, phase7)

    # Phase 8 — Write Draft + Report
    phase8 = _phase8_write_and_report(
        batch_id, problem_id, product, severity, component,
        run_id, phase1, phase2, phase4, phase5, phase6, phase7
    )
    _save_phase(table, run_id, batch_id, 8, phase8)

    total_ms = int((time.time() - t_start) * 1000)
    final_status = "completed_with_gaps" if phase6.get("gaps_blocking") else "completed"
    _update_run(table, run_id, batch_id, {
        "status":               final_status,
        "current_phase":        8,
        "phases_completed":     [1, 2, 3, 4, 5, 6, 7, 8],
        "report_download_url":  phase8.get("report_download_url", ""),
        "wiki_rca_page_id":     phase8.get("wiki_rca_page_id", ""),
        "wiki_kedb_page_id":    phase8.get("wiki_kedb_page_id", ""),
        "total_latency_ms":     total_ms,
    })

    return _respond(200, {
        "run_id":               run_id,
        "status":               final_status,
        "phases_completed":     [1, 2, 3, 4, 5, 6, 7, 8],
        "total_latency_ms":     total_ms,
        "report_download_url":  phase8.get("report_download_url", ""),
        "wiki_rca_page_id":     phase8.get("wiki_rca_page_id", ""),
        "wiki_kedb_page_id":    phase8.get("wiki_kedb_page_id", ""),
        "phase_results": {
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
# Phase implementations
# ════════════════════════════════════════════════════════════════════════════

def _phase1_load_records(problem_id, product, component, batch_id, related_record_ids):
    """Programmatic — simulate record load from batch data."""
    records = []
    missing = []
    for rid in (related_record_ids or []):
        records.append({
            "id":                       rid,
            "source_type":              "Incident" if rid.upper().startswith("INC") else "Log",
            "summary_title":            f"Record {rid} linked to {problem_id}",
            "raw_excerpt":              f"Excerpt for {rid} in {component}",
            "solution":                 "",
            "normalized_issue_category": "",
        })

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
            inferenceConfig={"maxTokens": 300},
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


def _phase4_prior_knowledge(product, component, phase2):
    """SK-01: Load prior RCA pages and KEDB entries from wiki."""
    payload = {
        "inputs": {
            "customer_id": product,
            "domain":      "problem-management",
            "use_case":    "UC-PM",
            "component":   component,
            "category":    phase2.get("normalized_category", ""),
            "recurrence":  phase2.get("recurrence_type", ""),
        },
        "invoked_by": "pm-harness",
    }
    result = _invoke_skill(SK01_FUNCTION, payload, "SK-01")
    if not result:
        return {
            "prior_rcas":               [],
            "kedb_entries":             [],
            "playbooks":                [],
            "prior_knowledge_confidence": "none",
        }
    outputs     = result.get("outputs", result)
    prior_pages = outputs.get("prior_contributions", []) or outputs.get("wiki_pages", [])
    playbook    = outputs.get("playbook", {})
    playbooks   = [playbook] if isinstance(playbook, dict) and playbook else []
    confidence  = "low" if not prior_pages else "medium"
    return {
        "prior_rcas":               prior_pages,
        "kedb_entries":             [],
        "playbooks":                playbooks,
        "prior_knowledge_confidence": confidence,
    }


def _phase5_rca_draft(phase1, phase2, sme_context, phase4):
    """SK-02: Draft RCA narrative with pattern detection."""
    problem_record  = phase1.get("problem_record", {})
    related_records = phase1.get("related_records", [])
    prior_rcas      = phase4.get("prior_rcas", [])
    kedb_entries    = phase4.get("kedb_entries", [])

    records_text = "\n".join(
        f"- [{r.get('source_type','')}] {r.get('summary_title','')}: {r.get('raw_excerpt','')[:200]}"
        for r in related_records[:20]
    ) or "(none)"
    prior_text = "\n".join(
        f"- {p.get('title','') if isinstance(p, dict) else str(p)}"
        + (f": {p.get('summary','')[:150]}" if isinstance(p, dict) else "")
        for p in prior_rcas[:5]
    ) or "(none)"

    prompt = f"""You are a Problem Management analyst drafting a Root Cause Analysis.

PROBLEM: {problem_record.get('id','')} | {problem_record.get('product','')} / {problem_record.get('component','')}
CATEGORY: {phase2.get('normalized_category','')}
RECURRENCE: {phase2.get('recurrence_type','')}
RISK TIER: {phase2.get('risk_tier','')}

SME CONTEXT:
{sme_context or "(not provided)"}

RELATED RECORDS:
{records_text}

PRIOR RCAs:
{prior_text}

Produce a structured RCA. Return ONLY valid JSON (no markdown):
{{
  "root_cause_statement": "1-3 sentence root cause narrative",
  "contributing_factors": ["factor 1", "factor 2"],
  "timeline": [{{"timestamp": "ISO or relative", "record_id": "", "description": ""}}],
  "pattern_detected": true|false,
  "pattern_description": "description or empty string",
  "linked_problem_ids": ["PRB-xxx"],
  "corrective_actions": [{{"type": "workaround|permanent_fix", "description": "", "owner": ""}}],
  "rca_confidence": "high|medium|low"
}}"""

    try:
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 1500},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE)
        m   = re.search(r'\{.*\}', raw.strip(), re.DOTALL)
        if m:
            return json.loads(m.group())
    except json.JSONDecodeError as e:
        print(f"WARN: RCA JSON parse failed: {e} — attempting field extraction")
        # Best-effort field extraction from raw LLM text
        def _extract(field, default=""):
            pat = rf'"{field}"\s*:\s*"([^"]*)"'
            mo = re.search(pat, raw)
            return mo.group(1) if mo else default
        return {
            "root_cause_statement": _extract("root_cause_statement", raw[:300]),
            "contributing_factors": [],
            "timeline":             [],
            "pattern_detected":     False,
            "pattern_description":  "",
            "linked_problem_ids":   [],
            "corrective_actions":   [{"type": "workaround", "description": "See raw notes", "owner": "SME"}],
            "rca_confidence":       "low",
        }
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
    """SK-05: Detect knowledge gaps in the RCA draft."""
    root_cause  = phase5.get("root_cause_statement", "")
    confidence  = phase5.get("rca_confidence", "low")
    actions     = phase5.get("corrective_actions", [])

    question = (
        f"Review this RCA for problem {problem_id} ({product}).\n"
        f"Root cause: {root_cause}\n"
        f"RCA confidence: {confidence}\n"
        f"Corrective actions: {json.dumps(actions[:5])}\n"
        "Identify knowledge gaps: missing evidence, incomplete root cause chains, "
        "missing permanent fix details, missing monitoring or prevention steps."
    )
    payload = {
        "inputs": {
            "question":    question,
            "domain":      "problem-management",
            "use_case":    "UC-PM",
            "customer_id": product,
            "low_confidence_response": {
                "confidence": confidence,
            },
        },
        "invoked_by": "pm-harness",
    }
    result = _invoke_skill(SK05_FUNCTION, payload, "SK-05")
    if not result:
        return {"gaps": [], "gap_count": 0, "gaps_blocking": False}
    outputs = result.get("outputs", result)
    return {
        "gaps":          outputs.get("gaps", []),
        "gap_count":     outputs.get("gap_count", 0),
        "gaps_blocking": outputs.get("blocking", False),
    }


def _phase7_template_fill(phase1, phase2, phase5, phase6):
    """SK-04: Populate RCA and KEDB templates."""
    problem_record = phase1.get("problem_record", {})
    prompt = f"""Populate a standard RCA document template and a KEDB entry template.

INPUTS:
- Problem: {problem_record.get('id','')} | {problem_record.get('product','')}
- Category: {phase2.get('normalized_category','')}
- Risk tier: {phase2.get('risk_tier','')}
- Root cause: {phase5.get('root_cause_statement','')}
- Contributing factors: {json.dumps(phase5.get('contributing_factors',[]))}
- Timeline: {json.dumps(phase5.get('timeline',[])[:5])}
- Corrective actions: {json.dumps(phase5.get('corrective_actions',[]))}
- Pattern: {phase5.get('pattern_description','')}
- Gaps: {json.dumps([g.get('description','') for g in phase6.get('gaps',[])][:3])}

Mark fields that cannot be filled as "Pending — requires SME input".

Return ONLY valid JSON (no markdown):
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
            inferenceConfig={"maxTokens": 1500},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE)
        m   = re.search(r'\{.*\}', raw.strip(), re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"WARN: template fill failed: {e}")

    return {
        "rca_document":   {"title": f"RCA - {phase1.get('problem_record',{}).get('id','')}", "status": "Draft"},
        "kedb_entry":     {"title": f"KEDB - {phase1.get('problem_record',{}).get('id','')}", "status": "Draft"},
        "unfilled_fields": ["All fields — template fill failed; raw Phase 5 output available"],
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

    report_download_url = _presign(PM_WIKI_BUCKET, report_key)

    return {
        "wiki_rca_page_id":  rca_key,
        "wiki_kedb_page_id": kedb_key,
        "report_s3_key":          report_key,
        "report_download_url":    report_download_url,
        "indexed":                bool(rca_key),
        "status":                 "completed_with_gaps" if blocking else "completed",
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
    rel_records  = phase1.get("related_records", [])
    actions      = phase5.get("corrective_actions", [])
    factors      = phase5.get("contributing_factors", [])
    timeline     = phase5.get("timeline", [])
    linked_ids   = phase5.get("linked_problem_ids", [])
    pattern_det  = phase5.get("pattern_detected", False)
    pattern_desc = phase5.get("pattern_description", "")
    unfilled     = phase7.get("unfilled_fields", [])

    sev_color = {"P1": "#dc2626", "High": "#dc2626", "P2": "#f59e0b",
                 "Medium": "#f59e0b", "P3": "#16a34a", "Low": "#16a34a"}.get(severity, "#6b7280")
    risk_color = {"high": "#dc2626", "medium": "#f59e0b", "low": "#16a34a"}.get(
        phase2.get("risk_tier", "low"), "#6b7280")
    status_label = "⚠ Draft — Incomplete (Blocking Gaps)" if blocking else "Draft"
    status_color = "#dc2626" if blocking else "#2563eb"

    def li_list(items):
        return "".join(f"<li>{i}</li>" for i in items) if items else "<li>(none)</li>"

    def action_rows(acts):
        rows = ""
        for a in acts:
            badge = (
                '<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:4px">permanent fix</span>'
                if a.get("type") == "permanent_fix"
                else '<span style="background:#fef9c3;color:#854d0e;padding:2px 8px;border-radius:4px">workaround</span>'
            )
            rows += f"<tr><td>{badge}</td><td>{a.get('description','')}</td><td>{a.get('owner','')}</td></tr>"
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
            rows += f"<tr><td>{e.get('timestamp','')}</td><td>{e.get('record_id','')}</td><td>{e.get('description','')}</td></tr>"
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
        linked_str = ", ".join(linked_ids) if linked_ids else "(none)"
        pattern_html = (
            f"<h2>5. Recurrence Pattern</h2>"
            f"<p>{pattern_desc}</p>"
            f"<p><strong>Linked prior problems:</strong> {linked_str}</p>"
        )

    prior_html = ""
    if prior_rcas:
        items = "".join(
            f"<li>{p.get('title','') or p.get('id','') if isinstance(p, dict) else str(p)}</li>"
            for p in prior_rcas[:10]
        )
        prior_html = f"<h2>10. Prior Related Problems</h2><ul>{items}</ul>"

    unfilled_html = ""
    if unfilled:
        items = "".join(f"<li>{f}</li>" for f in unfilled)
        unfilled_html = (
            f'<div style="background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px;margin:12px 0">'
            f"<strong>Pending fields (require SME input):</strong><ul>{items}</ul></div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PM RCA Report — {problem_id}</title>
<style>
  body{{font-family:Arial,sans-serif;max-width:900px;margin:40px auto;color:#1f2937;padding:0 20px}}
  h1{{color:#1e3a5f}} h2{{color:#374151;border-bottom:1px solid #e5e7eb;padding-bottom:6px}}
  table{{width:100%;border-collapse:collapse;margin:12px 0}}
  th,td{{border:1px solid #e5e7eb;padding:8px 12px;text-align:left}}
  th{{background:#f3f4f6}} .badge{{padding:3px 10px;border-radius:4px;font-weight:600}}
  ul{{margin:4px 0}} li{{margin:2px 0}}
</style>
</head>
<body>
<h1>Problem Management RCA Report</h1>
<p style="color:{status_color};font-weight:bold;font-size:1.1em">{status_label}</p>

<h2>1. Problem Summary</h2>
<table>
  <tr><th>Field</th><th>Value</th></tr>
  <tr><td>Problem ID</td><td><strong>{problem_id}</strong></td></tr>
  <tr><td>Batch ID</td><td>{batch_id}</td></tr>
  <tr><td>Run ID</td><td>{run_id}</td></tr>
  <tr><td>Product</td><td>{product}</td></tr>
  <tr><td>Component</td><td>{component}</td></tr>
  <tr><td>Severity</td><td><span class="badge" style="background:{sev_color};color:#fff">{severity}</span></td></tr>
  <tr><td>Risk Tier</td><td><span class="badge" style="background:{risk_color};color:#fff">{phase2.get('risk_tier','')}</span></td></tr>
  <tr><td>Category</td><td>{phase2.get('normalized_category','')}</td></tr>
  <tr><td>Recurrence</td><td>{phase2.get('recurrence_type','')}</td></tr>
  <tr><td>Classification Confidence</td><td>{phase2.get('classification_confidence','')}</td></tr>
</table>

<h2>2. Root Cause Statement</h2>
<p>{phase5.get('root_cause_statement','')}</p>

<h2>3. Contributing Factors</h2>
<ul>{li_list(factors)}</ul>

<h2>4. Incident Timeline</h2>
<table>
  <tr><th>Timestamp</th><th>Record ID</th><th>Description</th></tr>
  {tl_rows(timeline)}
</table>

{pattern_html}

<h2>6. Corrective Actions</h2>
<table>
  <tr><th>Type</th><th>Description</th><th>Owner</th></tr>
  {action_rows(actions)}
</table>

<h2>7. KEDB Entry (Draft)</h2>
{kedb_html}
{unfilled_html}

<h2>8. Knowledge Gaps</h2>
{gap_items(gaps)}

<h2>9. Evidence Pack</h2>
<table>
  <tr><th>Record ID</th><th>Source Type</th><th>Summary</th></tr>
  {rec_rows(rel_records)}
</table>

{prior_html}

<hr>
<p style="color:#6b7280;font-size:0.85em">
  Generated by LLMWiki PM Harness · Run {run_id} · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
  <br><strong>Status: DRAFT — NOT PUBLISHED. Review by Problem Coordinator required before publishing.</strong>
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


def _save_phase(table, run_id, batch_id, phase_num, result):
    existing = table.get_item(Key={"run_id": run_id, "batch_id": batch_id}).get("Item", {})
    saved    = json.loads(existing.get("phase_results", "{}"))
    saved[str(phase_num)] = result
    _update_run(table, run_id, batch_id, {
        "phase_results":  json.dumps(saved, default=str),
        "current_phase":  phase_num,
    })


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
