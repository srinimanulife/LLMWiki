import json
import os
import time
import boto3
from datetime import datetime, timezone, timedelta

bedrock       = boto3.client("bedrock-runtime",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb      = boto3.resource("dynamodb",
                                region_name=os.environ.get("AWS_REGION", "us-east-1"))
lambda_client = boto3.client("lambda",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))
sns           = boto3.client("sns",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))

WIKI_QUERY_FUNCTION  = os.environ.get("WIKI_QUERY_FUNCTION", "llmwiki-skill-sk02-wiki-query")
LOG_TABLE            = os.environ.get("LOG_TABLE", "llmwiki-log")
ISSUES_TABLE         = os.environ.get("ISSUES_TABLE", "llmwiki-claim-issues")
CLAIMS_SNS_TOPIC_ARN = os.environ.get("CLAIMS_SNS_TOPIC_ARN", "")
SKILL_ID             = "SK-06"
SKILL_NAME           = "ClaimReadinessSkill"
BUSINESS_NAME        = "Claim Readiness Validator"
MAX_CLAIM_LINES      = 500
HIGH_AMOUNT_THRESHOLD = 50000.0
STALE_DAYS           = 90


class _SkillError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def lambda_handler(event, context):
    t0 = time.time()

    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    inputs         = body.get("inputs", body)
    customer_id    = inputs.get("customer_id", "")
    claim_batch_id = inputs.get("claim_batch_id", "")
    claim_lines    = inputs.get("claim_lines", [])
    customer_type  = inputs.get("customer_type", "payer") or "payer"
    strict_mode    = bool(inputs.get("strict_mode", False))
    version        = body.get("version", "1.0")
    invoked_by     = body.get("invoked_by", "unknown-agent")
    use_case       = body.get("use_case", "UC5")

    try:
        if not customer_id:
            raise _SkillError("inputs.customer_id is required", 400)
        if not claim_batch_id:
            raise _SkillError("inputs.claim_batch_id is required", 400)

        if customer_type.lower() == "government":
            latency_ms = int((time.time() - t0) * 1000)
            outputs = {
                "readiness_score": None,
                "status": "not_applicable",
                "blocking_issues": [],
                "warnings": [],
                "lines_checked": 0,
                "lines_ready": 0,
            }
            _log_telemetry(SKILL_ID, SKILL_NAME, invoked_by, customer_id, use_case,
                           latency_ms, "success", claim_batch_id, 0, 0, 0, customer_type)
            return _skill_response(version, "success", outputs, latency_ms)

        if not claim_lines:
            raise _SkillError("claim_lines is empty — cannot proceed with readiness check", 400)

        if len(claim_lines) > MAX_CLAIM_LINES:
            raise _SkillError(
                f"claim_lines exceeds maximum of {MAX_CLAIM_LINES} lines (received {len(claim_lines)})",
                400
            )

        blocking_issues = []
        warnings        = []
        lines_ready     = 0
        now_date        = datetime.now(timezone.utc).date()
        stale_cutoff    = now_date - timedelta(days=STALE_DAYS)

        for line in claim_lines:
            claim_id      = line.get("claim_id", "UNKNOWN")
            service_date  = line.get("service_date", "")
            diagnosis_code = (line.get("diagnosis_code") or "").strip()
            amount        = float(line.get("amount", 0.0))

            line_blocking = []
            line_warn     = []

            if not diagnosis_code:
                line_blocking.append({
                    "claim_id":         claim_id,
                    "issue_type":       "missing_diagnosis_code",
                    "description":      "Diagnosis code is required for all claim lines",
                    "resolution_hint":  "Contact the provider to obtain ICD-10 code before resubmitting",
                })
            else:
                malformed = _is_malformed_diagnosis_code(diagnosis_code)
                if malformed:
                    classified_ok = _classify_diagnosis_code_with_bedrock(diagnosis_code, claim_id)
                    if not classified_ok:
                        line_warn.append(f"diagnosis_code_unverified for claim {claim_id}")
                    else:
                        if amount > HIGH_AMOUNT_THRESHOLD:
                            prior_auth_found = _check_prior_auth(customer_id, claim_id)
                            if not prior_auth_found:
                                line_blocking.append({
                                    "claim_id":        claim_id,
                                    "issue_type":      "missing_prior_auth",
                                    "description":     f"Amount ${amount:.2f} exceeds ${HIGH_AMOUNT_THRESHOLD:.0f} and no prior authorization found",
                                    "resolution_hint": "Obtain prior authorization from the payer before processing this claim line",
                                })
                else:
                    if amount > HIGH_AMOUNT_THRESHOLD:
                        prior_auth_found = _check_prior_auth(customer_id, claim_id)
                        if not prior_auth_found:
                            line_blocking.append({
                                "claim_id":        claim_id,
                                "issue_type":      "missing_prior_auth",
                                "description":     f"Amount ${amount:.2f} exceeds ${HIGH_AMOUNT_THRESHOLD:.0f} and no prior authorization found",
                                "resolution_hint": "Obtain prior authorization from the payer before processing this claim line",
                            })

            if service_date:
                try:
                    svc_date = datetime.strptime(service_date, "%Y-%m-%d").date()
                    if svc_date < stale_cutoff:
                        line_warn.append(
                            f"claim {claim_id} service_date {service_date} is more than {STALE_DAYS} days ago"
                        )
                except ValueError:
                    line_warn.append(f"claim {claim_id} has unparseable service_date '{service_date}'")

            if strict_mode:
                for w in line_warn:
                    line_blocking.append({
                        "claim_id":        claim_id,
                        "issue_type":      "warning_promoted_to_blocking",
                        "description":     w,
                        "resolution_hint": "Strict mode is enabled — resolve this warning before processing",
                    })
                line_warn = []

            blocking_issues.extend(line_blocking)
            warnings.extend(line_warn)

            if not line_blocking:
                lines_ready += 1

        lines_checked = len(claim_lines)
        readiness_score = int((lines_ready / lines_checked) * 100) if lines_checked > 0 else 0
        status = "ready" if not blocking_issues else "blocked"

        if blocking_issues:
            _persist_blocking_issues(blocking_issues, claim_batch_id, customer_id)
            _send_sns_alert(
                customer_id=customer_id,
                claim_batch_id=claim_batch_id,
                blocking_count=len(blocking_issues),
                readiness_score=readiness_score,
                error=None,
            )

        latency_ms = int((time.time() - t0) * 1000)

        outputs = {
            "readiness_score": readiness_score,
            "status":          status,
            "blocking_issues": blocking_issues,
            "warnings":        warnings,
            "lines_checked":   lines_checked,
            "lines_ready":     lines_ready,
        }

        _log_telemetry(SKILL_ID, SKILL_NAME, invoked_by, customer_id, use_case,
                       latency_ms, "success", claim_batch_id,
                       lines_checked, lines_ready, len(blocking_issues), customer_type)

        return _skill_response(version, "success", outputs, latency_ms)

    except _SkillError as e:
        latency_ms = int((time.time() - t0) * 1000)
        _send_sns_alert(
            customer_id=customer_id,
            claim_batch_id=claim_batch_id,
            blocking_count=0,
            readiness_score=0,
            error=str(e),
        )
        _log_telemetry(SKILL_ID, SKILL_NAME, invoked_by, customer_id, use_case,
                       latency_ms, "error", claim_batch_id, 0, 0, 0, customer_type)
        return _respond(e.status_code, {"error": str(e)})

    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        print(f"ERROR: Unhandled exception in {SKILL_NAME}: {e}")
        _send_sns_alert(
            customer_id=customer_id,
            claim_batch_id=claim_batch_id,
            blocking_count=0,
            readiness_score=0,
            error=str(e),
        )
        _log_telemetry(SKILL_ID, SKILL_NAME, invoked_by, customer_id, use_case,
                       latency_ms, "error", claim_batch_id, 0, 0, 0, customer_type)
        return _respond(500, {"error": "Internal skill error — see CloudWatch for details"})


def _is_malformed_diagnosis_code(code: str) -> bool:
    import re
    pattern = re.compile(r'^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$', re.IGNORECASE)
    return not bool(pattern.match(code.strip()))


def _classify_diagnosis_code_with_bedrock(diagnosis_code: str, claim_id: str) -> bool:
    try:
        prompt = (
            f"You are a medical coding expert. Is the following diagnosis code a recognizable "
            f"or plausible ICD-10 code, even if slightly malformed? Code: '{diagnosis_code}'. "
            f"Reply with only 'yes' or 'no'."
        )
        _converse_kwargs = {
            "modelId": os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 16},
        }
        response = bedrock.converse(**_converse_kwargs)
        answer = response["output"]["message"]["content"][0]["text"].strip().lower()
        return answer.startswith("yes")
    except Exception as e:
        print(f"WARN: Bedrock classification failed for claim {claim_id}, code '{diagnosis_code}': {e}")
        return False


def _check_prior_auth(customer_id: str, claim_id: str) -> bool:
    try:
        question = (
            f"Is there a prior authorization on file for customer {customer_id} claim {claim_id}?"
        )
        payload = json.dumps({
            "inputs": {
                "question":    question,
                "domain":      "claims-processing",
                "customer_id": customer_id,
                "use_case":    "UC5",
            },
            "version":    "1.0",
            "invoked_by": SKILL_NAME,
        })
        resp = lambda_client.invoke(
            FunctionName=WIKI_QUERY_FUNCTION,
            InvocationType="RequestResponse",
            Payload=payload.encode(),
        )
        raw = json.loads(resp["Payload"].read())
        if "body" in raw:
            inner = raw["body"]
            result = json.loads(inner) if isinstance(inner, str) else (inner or {})
        else:
            result = raw

        outputs    = result.get("outputs", result)
        confidence = outputs.get("confidence", "low")
        answer     = (outputs.get("answer") or outputs.get("response") or "").lower()

        if confidence == "low":
            print(f"WARN: wiki_query returned low confidence for prior auth check on claim {claim_id} — treating as no prior auth")
            return False

        positive_signals = ["prior auth", "prior authorization", "authorization found", "pa-", "approved"]
        return any(sig in answer for sig in positive_signals)

    except Exception as e:
        print(f"WARN: wiki_query failed for prior auth check on claim {claim_id}: {e}")
        return False


def _persist_blocking_issues(blocking_issues: list, claim_batch_id: str, customer_id: str):
    table     = dynamodb.Table(ISSUES_TABLE)
    ttl_value = int(time.time()) + STALE_DAYS * 86400
    now       = datetime.now(timezone.utc).isoformat()

    for issue in blocking_issues:
        attempts = 0
        last_exc = None
        while attempts < 3:
            try:
                table.put_item(Item={
                    "claim_id":        issue["claim_id"],
                    "timestamp_id":    f"{now}#{claim_batch_id}#{issue['issue_type']}",
                    "claim_batch_id":  claim_batch_id,
                    "customer_id":     customer_id,
                    "issue_type":      issue["issue_type"],
                    "description":     issue["description"],
                    "resolution_hint": issue["resolution_hint"],
                    "created_at":      now,
                    "expires_at":      ttl_value,
                })
                last_exc = None
                break
            except Exception as e:
                attempts += 1
                last_exc = e
                print(f"WARN: DynamoDB write attempt {attempts} failed for claim {issue['claim_id']}: {e}")
                time.sleep(0.2 * attempts)

        if last_exc is not None:
            raise _SkillError(
                f"DynamoDB write failed 3 times for claim {issue['claim_id']} — issues must be persisted before returning",
                500,
            )


def _send_sns_alert(customer_id: str, claim_batch_id: str,
                    blocking_count: int, readiness_score: int, error):
    if not CLAIMS_SNS_TOPIC_ARN:
        print("WARN: CLAIMS_SNS_TOPIC_ARN not configured — skipping SNS alert")
        return
    try:
        if error:
            subject = f"[{SKILL_NAME}] Hard failure — {claim_batch_id}"
            message = (
                f"Skill: {SKILL_NAME} ({SKILL_ID})\n"
                f"Customer: {customer_id}\n"
                f"Batch: {claim_batch_id}\n"
                f"Error: {error}"
            )
        else:
            subject = f"[{SKILL_NAME}] Blocking issues — {claim_batch_id}"
            message = (
                f"Skill: {SKILL_NAME} ({SKILL_ID})\n"
                f"Customer: {customer_id}\n"
                f"Batch: {claim_batch_id}\n"
                f"Blocking issues: {blocking_count}\n"
                f"Readiness score: {readiness_score}%\n"
                f"Action required: resolve blocking issues before claim submission."
            )
        sns.publish(
            TopicArn=CLAIMS_SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message,
        )
    except Exception as e:
        print(f"WARN: SNS publish failed (non-fatal): {e}")


def _log_telemetry(skill_id, skill_name, agent_id, customer_id, use_case,
                   latency_ms, status, claim_batch_id,
                   blocking_count, issues_count, readiness_score, customer_type):
    try:
        now = datetime.now(timezone.utc).isoformat()
        dynamodb.Table(LOG_TABLE).put_item(Item={
            "log_date":      now[:10],
            "timestamp_id":  f"{now}#{skill_id}",
            "skill_id":      skill_id,
            "skill_name":    skill_name,
            "agent_id":      agent_id,
            "customer_id":   customer_id,
            "use_case":      use_case,
            "latency_ms":    latency_ms,
            "status":        status,
            "claim_batch_id": claim_batch_id,
            "blocking_count": blocking_count,
            "issues_count":  issues_count,
            "readiness_score": readiness_score,
            "customer_type": customer_type,
            "expires_at":    int(time.time()) + 90 * 86400,
        })
    except Exception as e:
        print(f"WARN: telemetry log failed (non-fatal): {e}")


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
        "headers":    {"Content-Type": "application/json",
                       "Access-Control-Allow-Origin": "*"},
        "body":       json.dumps(payload, default=str),
    }


def _respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers":    {"Content-Type": "application/json",
                       "Access-Control-Allow-Origin": "*"},
        "body":       json.dumps(body),
    }