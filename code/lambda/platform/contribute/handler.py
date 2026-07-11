"""
Contribute Lambda — POST /wiki/contribute
Validates agent write-back contributions, creates wiki pages in S3,
updates DynamoDB index and contribution audit table, and triggers
a Bedrock KB ingestion job so the new page is immediately searchable.
"""

import json
import os
import re
import uuid
import boto3
from datetime import datetime, timezone

s3       = boto3.client("s3")
ssm      = boto3.client("ssm")
dynamodb = boto3.resource("dynamodb")
bedrock_agent = boto3.client("bedrock-agent",
                              region_name=os.environ.get("AWS_REGION", "us-east-1"))

WIKI_BUCKET   = os.environ["WIKI_BUCKET"]
INDEX_TABLE   = os.environ.get("DYNAMODB_INDEX",   "llmwiki-index")
CONTRIB_TABLE = os.environ.get("CONTRIB_TABLE",    "llmwiki-contributions")
KB_ID_PARAM   = os.environ.get("KB_ID_PARAM",      "/llmwiki/bedrock_kb_id")
KB_DS_PARAM   = os.environ.get("KB_DS_ID_PARAM",   "/llmwiki/bedrock_kb_datasource_id")

ALLOWED_PAGE_TYPES = {"customers", "decisions", "artifacts", "evidence", "sops", "runbooks"}

PENDING_PREFIX = "wiki/pending/"
WIKI_PREFIX    = "wiki/"


# ── Entry point ────────────────────────────────────────────────────

def lambda_handler(event, context):
    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    page_type    = body.get("page_type", "").strip()
    page_slug    = body.get("page_slug", "").strip()
    content      = body.get("content", "").strip()
    agent_id     = body.get("agent_id", "unknown-agent")
    customer_id  = body.get("customer_id", "")
    use_case     = body.get("use_case", "")
    human_review = body.get("human_review_required", False)

    # Validate
    errors = validate_contribution(page_type, page_slug, content)
    if errors:
        return respond(400, {"error": errors})

    # Auto-flag high-risk page types for human review
    if page_type in {"decisions", "evidence"}:
        human_review = True

    # Sanitise slug
    page_slug = re.sub(r"[^a-z0-9-]", "-", page_slug.lower()).strip("-")

    # Inject agent metadata into frontmatter if not present
    content = inject_frontmatter(content, agent_id, customer_id, use_case, page_type)

    # Write to S3
    prefix  = PENDING_PREFIX if human_review else f"{WIKI_PREFIX}{page_type}/"
    s3_key  = f"{prefix}{page_slug}.md"

    s3.put_object(
        Bucket=WIKI_BUCKET,
        Key=s3_key,
        Body=content.encode("utf-8"),
        ContentType="text/markdown",
    )

    now = datetime.now(timezone.utc).isoformat()

    # Update DynamoDB index
    effective_type = "pending" if human_review else page_type
    dynamodb.Table(INDEX_TABLE).put_item(Item={
        "page_type":          effective_type,
        "page_slug":          page_slug,
        "s3_key":             s3_key,
        "last_updated":       now,
        "contributing_agent": agent_id,
        "customer_id":        customer_id,
        "use_case":           use_case,
        "status":             "pending-review" if human_review else "active",
    })

    # Write to contribution audit table
    _write_audit(agent_id, page_type, page_slug, s3_key, customer_id, use_case,
                 human_review, now)

    # Trigger KB sync (non-fatal)
    if not human_review:
        _trigger_kb_sync()

    return respond(200, {
        "status":      "pending-review" if human_review else "indexed",
        "page_slug":   page_slug,
        "page_type":   page_type,
        "s3_uri":      f"s3://{WIKI_BUCKET}/{s3_key}",
        "human_review_required": human_review,
        "contributing_agent": agent_id,
        "timestamp":   now,
    })


# ── Validation ─────────────────────────────────────────────────────

def validate_contribution(page_type: str, page_slug: str, content: str) -> str:
    if not page_type:
        return "Missing page_type"
    if page_type not in ALLOWED_PAGE_TYPES:
        return f"page_type must be one of: {sorted(ALLOWED_PAGE_TYPES)}"
    if not page_slug:
        return "Missing page_slug"
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-_]{1,120}$", page_slug):
        return "page_slug must be 2-120 chars, letters/digits/hyphens/underscores"
    if not content or len(content.strip()) < 50:
        return "content is required and must be at least 50 characters"
    if len(content) > 500_000:
        return "content exceeds 500 KB limit"
    return ""


# ── Frontmatter injection ──────────────────────────────────────────

def inject_frontmatter(content: str, agent_id: str, customer_id: str,
                        use_case: str, page_type: str) -> str:
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fields_to_add = []

    if "contributing_agent:" not in content:
        fields_to_add.append(f"contributing_agent: {agent_id}")
    if customer_id and "customer_id:" not in content:
        fields_to_add.append(f"customer_id: {customer_id}")
    if use_case and "use_case_tags:" not in content:
        fields_to_add.append(f"use_case_tags: [{use_case}]")

    if not fields_to_add:
        return content

    if content.startswith("---"):
        # Insert inside existing frontmatter block
        end = content.find("\n---", 3)
        if end != -1:
            insert_at = end
            return (content[:insert_at]
                    + "\n" + "\n".join(fields_to_add)
                    + content[insert_at:])

    # Prepend new frontmatter block
    fm = "---\n"
    fm += f"date: {now_date}\n"
    fm += "\n".join(fields_to_add) + "\n"
    fm += "---\n\n"
    return fm + content


# ── Audit trail ────────────────────────────────────────────────────

def _write_audit(agent_id: str, page_type: str, page_slug: str, s3_key: str,
                 customer_id: str, use_case: str, human_review: bool, now: str):
    try:
        dynamodb.Table(CONTRIB_TABLE).put_item(Item={
            "contribution_id": str(uuid.uuid4()),
            "agent_id":        agent_id,
            "page_type":       page_type,
            "page_slug":       page_slug,
            "s3_key":          s3_key,
            "customer_id":     customer_id,
            "use_case":        use_case,
            "human_review":    human_review,
            "timestamp":       now,
            "status":          "pending-review" if human_review else "accepted",
        })
    except Exception as e:
        print(f"WARN: contribution audit write failed (non-fatal): {e}")


# ── KB sync ────────────────────────────────────────────────────────

def _trigger_kb_sync():
    try:
        kb_id = ssm.get_parameter(Name=KB_ID_PARAM)["Parameter"]["Value"]
        ds_id = ssm.get_parameter(Name=KB_DS_PARAM)["Parameter"]["Value"]
        bedrock_agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
        print("KB ingestion job started")
    except Exception as e:
        print(f"WARN: KB sync failed (non-fatal): {e}")


# ── Helpers ────────────────────────────────────────────────────────

def respond(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
