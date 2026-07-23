"""
UC-BC · Benefit Configuration Comparison Harness
8-phase deterministic workflow.
Compares two years of EOC PDFs and produces a structured diff table,
HTML report, and XLSX equivalent to a hand-authored analyst spreadsheet.

run_id = {plan_id}#{year_a}vs{year_b}
Output is always DRAFT — routed to wiki/pending/ via SK-03.
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

dynamodb      = boto3.resource("dynamodb",      region_name=_region)
lambda_client = boto3.client("lambda",          region_name=_region)
bedrock       = boto3.client("bedrock-runtime", region_name=_region)
s3_client     = boto3.client("s3",             region_name=_region,
                              config=Config(signature_version="s3v4"))

BC_RUNS_TABLE  = os.environ.get("BC_RUNS_TABLE",    "llmwiki-bc-runs")
WIKI_BUCKET    = os.environ.get("WIKI_BUCKET",      "")
MODEL_ID       = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
LOG_TABLE      = os.environ.get("LOG_TABLE",        "llmwiki-log")
REGISTRY_TABLE = os.environ.get("REGISTRY_TABLE",   "llmwiki-document-registry")

SK02_FUNCTION = os.environ.get("SK02_FUNCTION", "llmwiki-skill-wiki-query")
SK03_FUNCTION = os.environ.get("SK03_FUNCTION", "llmwiki-skill-wiki-contribute")
SK05_FUNCTION = os.environ.get("SK05_FUNCTION", "llmwiki-skill-gap-detection")

TTL_30_DAYS = 30 * 86400

CHANGE_CATEGORIES = {
    "increase": "COST_INCREASE",
    "decrease": "COST_DECREASE",
    "new":      "NEW_BENEFIT",
    "removed":  "REMOVED_BENEFIT",
    "changed":  "ADMINISTRATIVE",
}


# ════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════

def lambda_handler(event, context):
    raw_body = event.get("body") if "body" in event else None
    body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or event)

    action = body.get("action", "start")

    if action == "get_status":
        run_id  = body.get("run_id", "")
        plan_id = body.get("plan_id", "")
        if not run_id or "#" not in run_id:
            return _respond(400, {"error": "run_id required"})
        parts    = run_id.split("#", 1)
        plan_id  = parts[0]
        yearkey  = parts[1]
        table    = dynamodb.Table(BC_RUNS_TABLE)
        item     = table.get_item(Key={"run_id": run_id, "plan_id": plan_id}).get("Item", {})
        if not item:
            return _respond(404, {"error": f"run {run_id} not found"})
        raw_pr        = item.get("phase_results", "{}")
        phase_results = json.loads(raw_pr) if isinstance(raw_pr, str) else (raw_pr or {})
        p8            = phase_results.get("8", {})
        return _respond(200, {
            "run_id":              run_id,
            "status":              item.get("status"),
            "current_phase":       item.get("current_phase"),
            "phases_completed":    item.get("phases_completed", []),
            "differences_found":   p8.get("differences_found", 0),
            "report_download_url": p8.get("report_url", ""),
            "xlsx_download_url":   p8.get("xlsx_url", ""),
        })

    plan_id = (body.get("plan_id") or "").strip()
    year_a  = (body.get("year_a")  or "").strip()
    year_b  = (body.get("year_b")  or "").strip()
    chapters = body.get("chapters", [])

    if not plan_id:
        return _respond(400, {"error": "plan_id is required"})
    if not year_a or not year_b:
        return _respond(400, {"error": "year_a and year_b are required"})
    if year_a == year_b:
        return _respond(400, {"error": "year_a and year_b must differ"})

    run_id  = f"{plan_id}#{year_a}vs{year_b}"
    table   = dynamodb.Table(BC_RUNS_TABLE)

    if action == "resume":
        existing = table.get_item(Key={"run_id": run_id, "plan_id": plan_id}).get("Item", {})
        if existing and existing.get("status") == "paused":
            return _resume_workflow(table, existing, plan_id, year_a, year_b, chapters, run_id)
        return _respond(400, {"error": f"No paused run found for {run_id}"})

    return _start_workflow(table, plan_id, year_a, year_b, chapters, run_id)


# ════════════════════════════════════════════════════════════════════════════
# Start path — Phases 1-4, pause
# ════════════════════════════════════════════════════════════════════════════

def _start_workflow(table, plan_id, year_a, year_b, chapters, run_id):
    now_iso = datetime.now(timezone.utc).isoformat()
    _init_run(table, run_id, plan_id, {
        "plan_id":    plan_id,
        "year_a":     year_a,
        "year_b":     year_b,
        "chapters":   json.dumps(chapters),
        "created_at": now_iso,
    })

    t_start = time.time()

    try:
        # ── Phase 1 — Validate document index ────────────────────────────────
        phase1 = _phase1_validate_docs(plan_id, year_a, year_b, chapters)
        _save_phase(table, run_id, plan_id, 1, phase1)

        # ── Phase 2 — Extract year_a benefit values ───────────────────────────
        phase2 = _phase2_extract_year(year_a, plan_id, chapters)
        _save_phase(table, run_id, plan_id, 2, phase2)

        # ── Phase 3 — Extract year_b benefit values ───────────────────────────
        phase3 = _phase3_extract_year(year_b, plan_id, chapters)
        _save_phase(table, run_id, plan_id, 3, phase3)

        # ── Phase 4 — Claude diff synthesis ──────────────────────────────────
        phase4 = _phase4_diff_synthesis(phase2, phase3, year_a, year_b, plan_id)
        _save_phase(table, run_id, plan_id, 4, phase4)

    except Exception as exc:
        _update_run(table, run_id, plan_id, {"status": "error", "error": str(exc)})
        return _respond(500, {"error": str(exc), "run_id": run_id})

    diffs_found = len(phase4.get("differences", []))
    _update_run(table, run_id, plan_id, {
        "status":        "paused",
        "current_phase": 4,
        "phases_completed": [1, 2, 3, 4],
    })

    return _respond(200, {
        "run_id":            run_id,
        "status":            "paused",
        "phase":             4,
        "differences_found": diffs_found,
        "year_a_items":      phase2.get("item_count", 0),
        "year_b_items":      phase3.get("item_count", 0),
        "latency_ms":        int((time.time() - t_start) * 1000),
        "message":           (
            f"Preliminary comparison complete. Found {diffs_found} differences between "
            f"{year_a} and {year_b}. Call action=resume to categorise and generate report."
        ),
    })


# ════════════════════════════════════════════════════════════════════════════
# Resume path — Phases 5-8
# ════════════════════════════════════════════════════════════════════════════

def _resume_workflow(table, existing, plan_id, year_a, year_b, chapters, run_id):
    raw_pr        = existing.get("phase_results", "{}")
    phase_results = json.loads(raw_pr) if isinstance(raw_pr, str) else (raw_pr or {})
    phase4        = phase_results.get("4", {})

    t_start = time.time()

    try:
        # ── Phase 5 — Gap detection ───────────────────────────────────────────
        phase5 = _phase5_gap_detection(phase4, year_a, year_b, plan_id)
        _save_phase(table, run_id, plan_id, 5, phase5)

        # ── Phase 6 — Categorise and rank differences ─────────────────────────
        phase6 = _phase6_categorise(phase4, year_a, year_b)
        _save_phase(table, run_id, plan_id, 6, phase6)

        # ── Phase 7 — Write diff draft to wiki ───────────────────────────────
        phase7 = _phase7_wiki_contribute(phase6, plan_id, year_a, year_b)
        _save_phase(table, run_id, plan_id, 7, phase7)

        # ── Phase 8 — Generate report + XLSX + presigned URLs ────────────────
        phase8 = _phase8_generate_report(
            plan_id, year_a, year_b, phase6, phase5
        )
        _save_phase(table, run_id, plan_id, 8, phase8)

    except Exception as exc:
        _update_run(table, run_id, plan_id, {"status": "error", "error": str(exc)})
        return _respond(500, {"error": str(exc), "run_id": run_id})

    total_diffs = len(phase6.get("differences", []))
    high_count  = len([d for d in phase6.get("differences", []) if d.get("severity") == "HIGH"])

    _update_run(table, run_id, plan_id, {
        "status":            "completed",
        "current_phase":     8,
        "phases_completed":  [1, 2, 3, 4, 5, 6, 7, 8],
        "total_latency_ms":  int((time.time() - t_start) * 1000),
    })

    _write_audit(plan_id, year_a, year_b, run_id, total_diffs, high_count, phase8)

    return _respond(200, {
        "run_id":              run_id,
        "status":              "completed",
        "differences_found":   total_diffs,
        "high_severity_count": high_count,
        "gaps_detected":       phase5.get("gap_count", 0),
        "latency_ms":          int((time.time() - t_start) * 1000),
        "artifacts": {
            "html_report":    phase8.get("report_url", ""),
            "xlsx_report":    phase8.get("xlsx_url", ""),
            "member_summary": phase8.get("summary_url", ""),
            "wiki_draft":     phase7.get("s3_uri", ""),
        },
    })


# ════════════════════════════════════════════════════════════════════════════
# Phase implementations
# ════════════════════════════════════════════════════════════════════════════

def _phase1_validate_docs(plan_id, year_a, year_b, chapters):
    """Check document registry — both years must be converted and indexed."""
    validated = []
    missing   = []

    if REGISTRY_TABLE:
        try:
            reg = dynamodb.Table(REGISTRY_TABLE)
            for year in [year_a, year_b]:
                resp = reg.scan(
                    FilterExpression="contains(source_key, :yr) AND #st = :done",
                    ExpressionAttributeNames={"#st": "status"},
                    ExpressionAttributeValues={":yr": year, ":done": "converted"},
                )
                items = resp.get("Items", [])
                if items:
                    validated.append({"year": year, "docs_found": len(items)})
                else:
                    missing.append(year)
        except Exception as e:
            print(f"WARN: registry check failed: {e}")

    return {
        "plan_id":   plan_id,
        "year_a":    year_a,
        "year_b":    year_b,
        "validated": validated,
        "missing":   missing,
        "chapters":  chapters or ["all"],
        "note":      "Missing years will be queried anyway — KB may still have content" if missing else "All docs confirmed indexed",
    }


def _phase2_extract_year(year, plan_id, chapters):
    """Extract all benefit line items for year_a via WikiQuery (SK-02)."""
    chapter_scope = (
        f"Chapters: {', '.join(chapters)}." if chapters else "all chapters"
    )
    question = (
        f"List ALL benefit line items from the {year} Evidence of Coverage "
        f"Medical Benefits Chart for plan {plan_id}, covering {chapter_scope}. "
        f"For EVERY service category provide: exact service name, copayment amount "
        f"or coinsurance percentage, any annual maximum or frequency limit, and "
        f"whether prior authorization is required. Include Part D drug benefit "
        f"thresholds (deductible, initial coverage limit, catastrophic stage). "
        f"Format as a numbered list with exact dollar amounts. Do not summarise — "
        f"list every row."
    )
    payload = {
        "skill":   "WikiQuerySkill",
        "version": "1.0",
        "inputs": {
            "question":    question,
            "domain":      "benefit-configuration",
            "customer_id": plan_id,
            "year_filter": year,
            "use_case":    "UC-BC",
            "intent":      "benefit-extraction",
        },
    }
    result = _invoke_skill(SK02_FUNCTION, payload, f"SK-02 year={year}")
    answer = (result or {}).get("answer", f"No {year} benefit data found in knowledge base.")

    lines = [l.strip() for l in answer.split("\n") if l.strip()]
    return {
        "year":       year,
        "answer":     answer,
        "item_count": len(lines),
        "latency_ms": (result or {}).get("latency_ms", 0),
    }


def _phase3_extract_year(year, plan_id, chapters):
    """Extract all benefit line items for year_b — same query, different year."""
    return _phase2_extract_year(year, plan_id, chapters)


def _phase4_diff_synthesis(phase2, phase3, year_a, year_b, plan_id):
    """Direct Bedrock call — Claude compares the two year extracts line by line."""
    answer_a = phase2.get("answer", "")
    answer_b = phase3.get("answer", "")

    prompt = f"""You are a healthcare benefit analyst comparing two plan years for {plan_id}.

YEAR {year_a} BENEFIT VALUES:
{answer_a}

YEAR {year_b} BENEFIT VALUES:
{answer_b}

Instructions:
1. Compare every benefit line item from {year_a} against {year_b} side by side.
2. Identify ALL differences — copayment changes, coinsurance changes, annual maximum
   changes, frequency changes (e.g. yearly → every 2 years), new benefits added,
   benefits removed, deductible changes, threshold changes, org/vendor changes.
3. Ignore purely formatting differences. Focus only on value or rule changes.
4. For each difference output a JSON object with EXACTLY these fields:
   {{
     "chapter": "Chapter N: <chapter name>",
     "section_category": "<exact service or benefit name>",
     "year_a_value": "<exact {year_a} value or rule>",
     "year_b_value": "<exact {year_b} value or rule>",
     "change_direction": "increase" | "decrease" | "new" | "removed" | "changed",
     "dollar_impact": <numeric dollar change or null if not applicable>,
     "summary": "<one plain-English sentence a Medicare member would understand>"
   }}
5. Include EVERY difference no matter how small.
6. Return ONLY a valid JSON array. No markdown fences, no explanation.
"""

    t0 = time.time()
    try:
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 8192, "temperature": 0},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        # Strip markdown fences if Claude wraps anyway
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        differences = json.loads(raw)
        if not isinstance(differences, list):
            differences = [differences]
    except json.JSONDecodeError:
        differences = _fallback_parse_diff(raw, year_a, year_b)
    except Exception as e:
        print(f"WARN: Phase 4 Bedrock call failed: {e}")
        differences = []

    return {
        "differences":   differences,
        "diff_count":    len(differences),
        "latency_ms":    int((time.time() - t0) * 1000),
    }


def _fallback_parse_diff(raw_text, year_a, year_b):
    """Best-effort extraction when Claude doesn't return clean JSON."""
    diffs = []
    try:
        objects = re.findall(r'\{[^{}]+\}', raw_text, re.DOTALL)
        for obj_str in objects:
            try:
                obj = json.loads(obj_str)
                if "section_category" in obj:
                    diffs.append(obj)
            except Exception:
                pass
    except Exception:
        pass
    return diffs


def _phase5_gap_detection(phase4, year_a, year_b, plan_id):
    """SK-05 — detect benefit categories that couldn't be compared."""
    diffs = phase4.get("differences", [])
    question = (
        f"Are there benefit categories present in the {year_a} EOC for {plan_id} "
        f"that are missing or incomplete in the {year_b} index? "
        f"Specifically check: Part D drug tiers, Durable Medical Equipment, "
        f"Mental Health/Substance Abuse, Preventive Care, and Vision services."
    )
    payload = {
        "skill":   "GapDetectionSkill",
        "version": "1.0",
        "inputs": {
            "question":                question,
            "domain":                  "benefit-configuration",
            "use_case":                "UC-BC",
            "customer_id":             plan_id,
            "low_confidence_response": {"confidence": "medium", "source": "benefit-comparison"},
        },
    }
    result = _invoke_skill(SK05_FUNCTION, payload, "SK-05")
    result = result or {}
    return {
        "skill_id":  "SK-05",
        "gap_count": result.get("gap_count", 0),
        "blocking":  result.get("blocking", False),
        "gaps":      result.get("gaps", []),
        "latency_ms": result.get("latency_ms", 0),
    }


def _phase6_categorise(phase4, year_a, year_b):
    """Direct Bedrock call — add category and severity to each difference."""
    diffs = phase4.get("differences", [])
    if not diffs:
        return {"differences": [], "latency_ms": 0}

    prompt = f"""Given this array of benefit differences between {year_a} and {year_b}:

{json.dumps(diffs, indent=2)}

For each object, add two new fields:
- "category": one of COST_INCREASE | COST_DECREASE | COVERAGE_REDUCTION |
               COVERAGE_EXPANSION | ADMINISTRATIVE | NEW_BENEFIT | REMOVED_BENEFIT
  Rules:
  - copayment goes up → COST_INCREASE
  - copayment goes down → COST_DECREASE
  - annual max decreases or frequency worsens → COVERAGE_REDUCTION
  - annual max increases or frequency improves → COVERAGE_EXPANSION
  - org name changes, deadline changes, vendor changes → ADMINISTRATIVE
  - brand new service added → NEW_BENEFIT
  - service eliminated → REMOVED_BENEFIT

- "severity": HIGH | MEDIUM | LOW
  Rules:
  - |dollar_impact| >= 20 OR coverage reduction of $500+ → HIGH
  - |dollar_impact| 5-19 OR any frequency change → MEDIUM
  - |dollar_impact| < 5 OR administrative only → LOW

Return ONLY the modified JSON array with category and severity added to each object.
No markdown fences, no explanation.
"""
    t0 = time.time()
    try:
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 8192, "temperature": 0},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        categorised = json.loads(raw)
        if not isinstance(categorised, list):
            categorised = diffs
    except Exception as e:
        print(f"WARN: Phase 6 categorisation failed: {e}")
        for d in diffs:
            d.setdefault("category", CHANGE_CATEGORIES.get(d.get("change_direction", ""), "ADMINISTRATIVE"))
            d.setdefault("severity", "MEDIUM" if abs(d.get("dollar_impact") or 0) >= 10 else "LOW")
        categorised = diffs

    return {
        "differences": categorised,
        "diff_count":  len(categorised),
        "latency_ms":  int((time.time() - t0) * 1000),
    }


def _phase7_wiki_contribute(phase6, plan_id, year_a, year_b):
    """SK-03 — write the structured diff as a DRAFT wiki page for human review."""
    diffs   = phase6.get("differences", [])
    content = _build_diff_markdown(diffs, plan_id, year_a, year_b)
    slug    = f"benefitconfig-{plan_id.lower()}-{year_a}-vs-{year_b}"

    payload = {
        "skill":   "WikiContributeSkill",
        "version": "1.0",
        "inputs": {
            "page_type":             "decisions",
            "page_slug":             slug,
            "content":               content,
            "agent_id":              "llmwiki-benefitconfig-harness",
            "customer_id":           plan_id,
            "use_case":              "UC-BC",
            "human_review_required": True,
        },
    }
    result = _invoke_skill(SK03_FUNCTION, payload, "SK-03") or {}
    return {
        "skill_id":    "SK-03",
        "page_slug":   slug,
        "page_status": result.get("status", "pending-review"),
        "s3_uri":      result.get("s3_uri", f"s3://{WIKI_BUCKET}/wiki/pending/decisions/{slug}.md"),
        "latency_ms":  result.get("latency_ms", 0),
    }


def _phase8_generate_report(plan_id, year_a, year_b, phase6, phase5):
    """Build HTML report + XLSX-style CSV, write to S3, return presigned URLs."""
    diffs       = phase6.get("differences", [])
    gaps        = phase5.get("gaps", [])
    run_date    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id_short = f"{plan_id}-{year_a}vs{year_b}"

    high   = [d for d in diffs if d.get("severity") == "HIGH"]
    medium = [d for d in diffs if d.get("severity") == "MEDIUM"]
    low    = [d for d in diffs if d.get("severity") == "LOW"]

    # ── HTML report ──────────────────────────────────────────────────────────
    html = _build_html_report(plan_id, year_a, year_b, diffs, high, medium, low, gaps, run_date)
    html_key = f"wiki/benefitconfig/reports/{run_id_short}/report.html"
    _s3_put(WIKI_BUCKET, html_key, html, "text/html")

    # ── CSV/XLSX-format diff (5 columns matching ground-truth xlsx) ───────────
    csv_lines = ["Chapter,Section/Category,{} Details,{} Details,Summary of Change".format(year_a, year_b)]
    for d in diffs:
        def esc(v): return str(v or "").replace('"', '""')
        csv_lines.append(
            f'"{esc(d.get("chapter",""))}",'
            f'"{esc(d.get("section_category",""))}",'
            f'"{esc(d.get("year_a_value",""))}",'
            f'"{esc(d.get("year_b_value",""))}",'
            f'"{esc(d.get("summary",""))}"'
        )
    csv_content = "\n".join(csv_lines)
    csv_key = f"wiki/benefitconfig/reports/{run_id_short}/differences.csv"
    _s3_put(WIKI_BUCKET, csv_key, csv_content, "text/csv")

    # ── Member summary markdown ───────────────────────────────────────────────
    summary_md = _build_member_summary(plan_id, year_a, year_b, high, medium, gaps, run_date)
    summary_key = f"wiki/benefitconfig/reports/{run_id_short}/member-summary.md"
    _s3_put(WIKI_BUCKET, summary_key, summary_md, "text/markdown")

    # ── Presigned URLs ────────────────────────────────────────────────────────
    expiry = 7 * 86400
    return {
        "report_url":  _presign(WIKI_BUCKET, html_key, expiry),
        "xlsx_url":    _presign(WIKI_BUCKET, csv_key,  expiry),
        "summary_url": _presign(WIKI_BUCKET, summary_key, expiry),
        "differences_found": len(diffs),
        "high_count":  len(high),
        "medium_count": len(medium),
        "low_count":   len(low),
        "gaps_count":  len(gaps),
    }


# ════════════════════════════════════════════════════════════════════════════
# Report builders
# ════════════════════════════════════════════════════════════════════════════

def _build_diff_markdown(diffs, plan_id, year_a, year_b):
    lines = [
        f"---",
        f"title: Benefit Configuration Diff — {plan_id} {year_a} vs {year_b}",
        f"date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"use_case_tags: [UC-BC]",
        f"status: DRAFT",
        f"contributing_agent: llmwiki-benefitconfig-harness",
        f"---",
        f"",
        f"# Benefit Changes: {plan_id} — {year_a} vs {year_b}",
        f"",
        f"**Status:** DRAFT — awaiting analyst review before publishing",
        f"**Differences found:** {len(diffs)}",
        f"",
        f"| Chapter | Section/Category | {year_a} | {year_b} | Change |",
        f"|---|---|---|---|---|",
    ]
    for d in diffs:
        def esc(v): return str(v or "").replace("|", "\\|")
        sev = d.get("severity", "")
        badge = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}.get(sev, "")
        lines.append(
            f"| {esc(d.get('chapter',''))} "
            f"| {esc(d.get('section_category',''))} "
            f"| {esc(d.get('year_a_value',''))} "
            f"| {esc(d.get('year_b_value',''))} "
            f"| {badge} {esc(d.get('summary',''))} |"
        )
    return "\n".join(lines)


def _build_member_summary(plan_id, year_a, year_b, high, medium, gaps, run_date):
    lines = [
        f"# Member Impact Summary — {plan_id}",
        f"**Plan years compared:** {year_a} vs {year_b}  |  **Date:** {run_date}",
        f"",
        f"## High-Impact Changes (Review Immediately)",
    ]
    if high:
        for d in high:
            lines.append(f"- **{d.get('section_category','')}**: {d.get('summary','')}")
    else:
        lines.append("- No high-severity changes detected.")

    lines += ["", "## Medium-Impact Changes"]
    if medium:
        for d in medium:
            lines.append(f"- **{d.get('section_category','')}**: {d.get('summary','')}")
    else:
        lines.append("- No medium-severity changes.")

    if gaps:
        lines += ["", "## Data Quality Notes"]
        lines.append("The following categories could not be fully compared due to indexing gaps:")
        for g in gaps:
            lines.append(f"- {g.get('title', str(g))}")

    return "\n".join(lines)


def _build_html_report(plan_id, year_a, year_b, diffs, high, medium, low, gaps, run_date):
    cost_increases = len([d for d in diffs if d.get("category") == "COST_INCREASE"])
    cost_decreases = len([d for d in diffs if d.get("category") == "COST_DECREASE"])

    rows = ""
    for d in diffs:
        sev   = d.get("severity", "LOW")
        color = {"HIGH": "#fee2e2", "MEDIUM": "#fef9c3", "LOW": "#f0fdf4"}.get(sev, "#fff")
        rows += (
            f"<tr style='background:{color}'>"
            f"<td>{d.get('chapter','')}</td>"
            f"<td><strong>{d.get('section_category','')}</strong></td>"
            f"<td>{d.get('year_a_value','')}</td>"
            f"<td>{d.get('year_b_value','')}</td>"
            f"<td>{d.get('category','')}</td>"
            f"<td>{sev}</td>"
            f"<td>{d.get('summary','')}</td>"
            f"</tr>\n"
        )

    gap_rows = "".join(
        f"<li>{g.get('title', str(g))}</li>" for g in gaps
    ) if gaps else "<li>None detected</li>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Benefit Diff — {plan_id} {year_a} vs {year_b}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2937; }}
  h1 {{ color: #1d4ed8; }}
  .summary-grid {{ display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }}
  .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
           padding: 16px 24px; min-width: 140px; text-align: center; }}
  .card .num {{ font-size: 2em; font-weight: bold; color: #1d4ed8; }}
  .card .lbl {{ font-size: .85em; color: #64748b; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 24px; font-size: .9em; }}
  th {{ background: #1d4ed8; color: #fff; padding: 10px 12px; text-align: left; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
  .badge-high {{ color: #dc2626; font-weight: bold; }}
  .badge-med  {{ color: #d97706; font-weight: bold; }}
  footer {{ margin-top: 40px; font-size: .8em; color: #94a3b8; }}
</style>
</head>
<body>
<h1>Benefit Configuration Change Report</h1>
<p><strong>Plan:</strong> {plan_id} &nbsp;|&nbsp;
   <strong>Comparing:</strong> {year_a} → {year_b} &nbsp;|&nbsp;
   <strong>Generated:</strong> {run_date}</p>
<p style="background:#fef3c7;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:4px;">
  ⚠️ <strong>DRAFT</strong> — This report is AI-generated and pending analyst review.
  Do not distribute to members before review.</p>

<div class="summary-grid">
  <div class="card"><div class="num">{len(diffs)}</div><div class="lbl">Total Changes</div></div>
  <div class="card"><div class="num" style="color:#dc2626">{len(high)}</div><div class="lbl">High Severity</div></div>
  <div class="card"><div class="num" style="color:#d97706">{len(medium)}</div><div class="lbl">Medium Severity</div></div>
  <div class="card"><div class="num" style="color:#16a34a">{len(low)}</div><div class="lbl">Low Severity</div></div>
  <div class="card"><div class="num" style="color:#dc2626">{cost_increases}</div><div class="lbl">Cost Increases</div></div>
  <div class="card"><div class="num" style="color:#16a34a">{cost_decreases}</div><div class="lbl">Cost Decreases</div></div>
</div>

<h2>All Differences</h2>
<table>
<thead><tr>
  <th>Chapter</th><th>Service / Category</th>
  <th>{year_a}</th><th>{year_b}</th>
  <th>Category</th><th>Severity</th><th>Summary</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>

<h2>Data Quality Notes</h2>
<ul>{gap_rows}</ul>

<footer>Generated by LLMWiki Benefit Configuration Harness (UC-BC) · {run_date}</footer>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════
# DynamoDB helpers
# ════════════════════════════════════════════════════════════════════════════

def _init_run(table, run_id, plan_id, extra):
    now_iso = datetime.now(timezone.utc).isoformat()
    item = {
        "run_id":           run_id,
        "plan_id":          plan_id,
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


def _update_run(table, run_id, plan_id, updates):
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_expr   = "SET " + ", ".join(f"#{k}=:{k}" for k in updates)
    expr_names = {f"#{k}": k for k in updates}
    expr_vals  = {f":{k}": v for k, v in updates.items()}
    table.update_item(
        Key={"run_id": run_id, "plan_id": plan_id},
        UpdateExpression=set_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_vals,
    )


def _save_phase(table, run_id, plan_id, phase_num, result):
    existing     = table.get_item(Key={"run_id": run_id, "plan_id": plan_id}).get("Item", {})
    saved        = json.loads(existing.get("phase_results", "{}"))
    saved[str(phase_num)] = result
    _update_run(table, run_id, plan_id, {
        "phase_results": json.dumps(saved, default=str),
        "current_phase": phase_num,
    })


def _write_audit(plan_id, year_a, year_b, run_id, total_diffs, high_count, phase8):
    if not LOG_TABLE:
        return
    try:
        now = datetime.now(timezone.utc)
        dynamodb.Table(LOG_TABLE).put_item(Item={
            "log_date":          f"session#benefitconfig#{now.strftime('%Y-%m-%d')}",
            "run_id":            run_id,
            "plan_id":           plan_id,
            "year_a":            year_a,
            "year_b":            year_b,
            "differences_found": total_diffs,
            "high_severity":     high_count,
            "report_url":        phase8.get("report_url", ""),
            "xlsx_url":          phase8.get("xlsx_url", ""),
            "created_at":        now.isoformat(),
            "expires_at":        int(time.time()) + 90 * 86400,
        })
    except Exception as e:
        print(f"WARN: audit write failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# Lambda / S3 helpers
# ════════════════════════════════════════════════════════════════════════════

def _invoke_skill(function_name, payload, skill_label):
    try:
        resp       = lambda_client.invoke(
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


def _s3_put(bucket, key, content, content_type="text/plain"):
    if not bucket:
        print(f"WARN: WIKI_BUCKET not set — skipping S3 write for {key}")
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


def _respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type":                "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
