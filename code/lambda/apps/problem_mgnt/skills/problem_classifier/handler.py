"""
SK-06 · Problem Classifier
Classifies a problem record into a normalized category, determines recurrence type
and risk tier, alerts ops team for P1/High severity via SNS.
Standard skill contract: {skill, version, inputs} → {skill, status, outputs, latency_ms}
"""

import json
import os
import re
import time
import uuid
import boto3
from datetime import datetime, timezone

bedrock  = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb",       region_name=os.environ.get("AWS_REGION", "us-east-1"))
sns      = boto3.client("sns",             region_name=os.environ.get("AWS_REGION", "us-east-1"))

MODEL_ID           = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
PM_CLASS_TABLE     = os.environ.get("PM_CLASS_TABLE",  "llmwiki-pm-classifications")
LOG_TABLE          = os.environ.get("LOG_TABLE",       "llmwiki-log")
SNS_TOPIC_ARN      = os.environ.get("PM_SNS_TOPIC_ARN", "")

SKILL_ID      = "SK-06"
SKILL_NAME    = "ProblemClassifierSkill"
BUSINESS_NAME = "Problem Classifier"

VALID_PRODUCTS    = {"QNXT", "TCS", "EAM", "EDM"}
VALID_CATEGORIES  = {
    "Batch Processing", "Integration", "Workflow", "Logging",
    "Authentication", "Eligibility", "Correspondence", "Encounter", "Status",
}
HIGH_SEVERITY     = {"P1", "High"}
MEDIUM_SEVERITY   = {"P2", "Medium"}


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or event)

    inputs          = body.get("inputs", body)
    version         = body.get("version", "1.0")
    invoked_by      = body.get("invoked_by", "unknown-agent")

    problem_id      = (inputs.get("problem_id") or "").strip()
    product         = (inputs.get("product")    or "").strip()
    component       = (inputs.get("component")  or "").strip()
    severity        = (inputs.get("severity")   or "").strip()
    problem_summary = (inputs.get("problem_summary") or "").strip()
    related_records = inputs.get("related_records", [])
    ingest_batch_id = (inputs.get("ingest_batch_id") or "").strip()

    # ── Hard validations ──────────────────────────────────────────────────────
    if not problem_id:
        return _respond(400, {"error": "problem_id is required"})
    if product not in VALID_PRODUCTS:
        return _respond(400, {"error": "product must be QNXT, TCS, EAM, or EDM"})
    if not isinstance(related_records, list):
        return _respond(400, {"error": "related_records must be a list"})
    if len(related_records) > 50:
        return _respond(400, {"error": "related_records exceeds maximum of 50"})

    # ── Risk tier from severity (deterministic, before LLM) ───────────────────
    if severity in HIGH_SEVERITY:
        risk_tier = "high"
    elif severity in MEDIUM_SEVERITY:
        risk_tier = "medium"
    else:
        risk_tier = "low"

    # ── Recurrence detection (keyword scan before LLM) ────────────────────────
    repeated_indicators = sum(
        1 for r in related_records
        if isinstance(r, dict) and "repeated" in (r.get("solution") or "").lower()
    )
    if len(related_records) == 0:
        recurrence_type = "unique"
        pre_confidence  = "low"
    elif repeated_indicators >= 2 or (
        repeated_indicators >= 1
        and len({r.get("normalized_issue_category", "") for r in related_records if isinstance(r, dict)}) < len(related_records)
    ):
        recurrence_type = "repeated"
        pre_confidence  = None  # let LLM decide
    else:
        recurrence_type = "unique"
        pre_confidence  = None

    # ── SNS alert for high severity (BEFORE LLM — spec says "immediately") ────
    alert_sent = False
    if risk_tier == "high" and SNS_TOPIC_ARN:
        alert_sent = _sns_alert(problem_id, product, component, severity,
                                 problem_summary, ingest_batch_id)

    # ── LLM classification ────────────────────────────────────────────────────
    normalized_category, classification_confidence, classification_notes = \
        _classify_with_llm(problem_id, product, component, severity,
                            problem_summary, related_records, recurrence_type,
                            pre_confidence)

    # ── Persist to DynamoDB (soft failure — do not abort) ─────────────────────
    _persist_classification(
        problem_id=problem_id,
        product=product,
        component=component,
        severity=severity,
        ingest_batch_id=ingest_batch_id,
        normalized_category=normalized_category,
        recurrence_type=recurrence_type,
        risk_tier=risk_tier,
        classification_confidence=classification_confidence,
        alert_sent=alert_sent,
        classification_notes=classification_notes,
        records_evaluated=len(related_records),
        repeated_indicators_found=repeated_indicators,
        invoked_by=invoked_by,
    )

    latency_ms = int((time.time() - t0) * 1000)
    _log_telemetry(invoked_by, problem_id, product, latency_ms)

    outputs = {
        "normalized_category":       normalized_category,
        "recurrence_type":           recurrence_type,
        "risk_tier":                 risk_tier,
        "classification_confidence": classification_confidence,
        "alert_sent":                alert_sent,
        "classification_notes":      classification_notes,
        "records_evaluated":         len(related_records),
        "repeated_indicators_found": repeated_indicators,
    }
    return _skill_response(version, "success", outputs, latency_ms)


# ────────────────────────────────────────────────────────────────────────────
# LLM classification
# ────────────────────────────────────────────────────────────────────────────

def _classify_with_llm(problem_id, product, component, severity,
                        problem_summary, related_records, recurrence_type,
                        pre_confidence) -> tuple:
    records_text = ""
    if related_records:
        for i, r in enumerate(related_records[:50], 1):
            if not isinstance(r, dict):
                continue
            records_text += (
                f"\nRecord {i}: [{r.get('source_type','')}] {r.get('summary_title','')}\n"
                f"  Excerpt: {r.get('raw_excerpt','')[:300]}\n"
                f"  Solution: {r.get('solution','')[:200]}\n"
                f"  Category hint: {r.get('normalized_issue_category','')}\n"
            )
    else:
        records_text = "\n(No related records provided — classify from problem summary only)"

    categories_list = ", ".join(sorted(VALID_CATEGORIES))
    prompt = f"""You are a Problem Management analyst classifying a technical problem record.

PROBLEM ID: {problem_id}
PRODUCT: {product}
COMPONENT: {component}
SEVERITY: {severity}
SUMMARY: {problem_summary}
RECURRENCE: {recurrence_type} (pre-determined by keyword scan)

RELATED RECORDS:
{records_text}

TASK:
1. Choose the BEST normalized_category from EXACTLY this list: {categories_list}
2. Assess classification_confidence: "high" if records clearly agree on one category, "medium" if partially ambiguous, "low" if minimal evidence
3. Write 1-2 sentences of classification_notes explaining your reasoning

Return ONLY valid JSON (no markdown):
{{
  "normalized_category": "<one of the listed categories>",
  "classification_confidence": "high"|"medium"|"low",
  "classification_notes": "<explanation>"
}}"""

    try:
        resp = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 400},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            raise ValueError("no JSON in LLM response")
        data = json.loads(m.group())
    except Exception as e:
        print(f"WARN: LLM classification failed: {e}")
        data = {
            "normalized_category":       "Workflow",
            "classification_confidence": "low",
            "classification_notes":      f"LLM classification unavailable ({e}). Defaulted to Workflow.",
        }

    # Map unknown category to closest valid value
    raw_cat = data.get("normalized_category", "Workflow")
    if raw_cat not in VALID_CATEGORIES:
        mapped = _map_to_closest_category(raw_cat)
        data["normalized_category"]       = mapped
        data["classification_confidence"] = "low"
        data["classification_notes"]      = (
            f"LLM returned unknown category '{raw_cat}'; mapped to '{mapped}'. "
            + (data.get("classification_notes") or "")
        )

    # Override confidence when pre-determined
    if pre_confidence == "low":
        data["classification_confidence"] = "low"
        if "no related records" not in (data.get("classification_notes") or "").lower():
            data["classification_notes"] = (
                "No related records provided. Category inferred from problem summary only. "
                "Confidence is low — recommend SME review of classification in Step 3."
            )

    return (
        data.get("normalized_category", "Workflow"),
        data.get("classification_confidence", "low"),
        data.get("classification_notes", ""),
    )


def _map_to_closest_category(raw: str) -> str:
    raw_lower = raw.lower()
    mapping = {
        "batch":          "Batch Processing",
        "integration":    "Integration",
        "workflow":       "Workflow",
        "log":            "Logging",
        "auth":           "Authentication",
        "eligib":         "Eligibility",
        "correspond":     "Correspondence",
        "encounter":      "Encounter",
        "status":         "Status",
    }
    for key, cat in mapping.items():
        if key in raw_lower:
            return cat
    return "Workflow"


# ────────────────────────────────────────────────────────────────────────────
# SNS alert
# ────────────────────────────────────────────────────────────────────────────

def _sns_alert(problem_id, product, component, severity,
               problem_summary, ingest_batch_id) -> bool:
    message = (
        f"HIGH SEVERITY PROBLEM ALERT\n\n"
        f"Problem ID:  {problem_id}\n"
        f"Product:     {product}\n"
        f"Component:   {component}\n"
        f"Severity:    {severity}\n"
        f"Batch:       {ingest_batch_id}\n\n"
        f"Summary:\n{problem_summary}\n\n"
        f"Action: Review classification at Step 3 and begin RCA immediately."
    )
    last_exc = None
    for attempt in range(1, 4):
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"[LLMWiki] {severity} Problem Alert: {problem_id} ({product})",
                Message=message,
            )
            return True
        except Exception as e:
            last_exc = e
            print(f"WARN: SNS attempt {attempt} failed: {e}")

    # 3 failures for P1/High → hard failure per spec
    raise RuntimeError(
        f"SNS publish failed 3 times for {severity} problem {problem_id}: {last_exc}"
    )


# ────────────────────────────────────────────────────────────────────────────
# Persistence
# ────────────────────────────────────────────────────────────────────────────

def _persist_classification(**kwargs):
    try:
        now = datetime.now(timezone.utc).isoformat()
        dynamodb.Table(PM_CLASS_TABLE).put_item(Item={
            "problem_id":                kwargs["problem_id"],
            "classified_at":             now,
            "product":                   kwargs["product"],
            "component":                 kwargs["component"],
            "severity":                  kwargs["severity"],
            "ingest_batch_id":           kwargs["ingest_batch_id"],
            "normalized_category":       kwargs["normalized_category"],
            "recurrence_type":           kwargs["recurrence_type"],
            "risk_tier":                 kwargs["risk_tier"],
            "classification_confidence": kwargs["classification_confidence"],
            "alert_sent":                kwargs["alert_sent"],
            "classification_notes":      kwargs["classification_notes"],
            "records_evaluated":         kwargs["records_evaluated"],
            "repeated_indicators_found": kwargs["repeated_indicators_found"],
            "invoked_by":                kwargs["invoked_by"],
            "ttl":                       int(time.time()) + 90 * 86400,
        })
    except Exception as e:
        print(f"WARN: DynamoDB write failed (non-fatal): {e}")


def _log_telemetry(agent_id, problem_id, product, latency_ms):
    try:
        now = datetime.now(timezone.utc).isoformat()
        dynamodb.Table(LOG_TABLE).put_item(Item={
            "log_date":     now[:10],
            "timestamp_id": f"{now}#{SKILL_ID}#{problem_id}",
            "skill_id":     SKILL_ID,
            "skill_name":   SKILL_NAME,
            "agent_id":     agent_id,
            "customer_id":  product,
            "use_case":     "UC-PM",
            "latency_ms":   latency_ms,
            "status":       "success",
            "expires_at":   int(time.time()) + 90 * 86400,
        })
    except Exception as e:
        print(f"WARN: telemetry log failed (non-fatal): {e}")


# ────────────────────────────────────────────────────────────────────────────
# Response helpers
# ────────────────────────────────────────────────────────────────────────────

def _skill_response(version, status, outputs, latency_ms):
    payload = {
        "skill":         SKILL_NAME,
        "business_name": BUSINESS_NAME,
        "skill_id":      SKILL_ID,
        "version":       version,
        "status":        status,
        "outputs":       outputs,
        "latency_ms":    latency_ms,
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(payload, default=str),
    }


def _respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
