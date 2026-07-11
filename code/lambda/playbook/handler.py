"""
Playbook Lambda — GET /wiki/playbook/{use-case}, GET /wiki/customer/{id}, GET /wiki/artifact/{type}
Assembles use-case playbooks and customer context pages dynamically from
the Bedrock KB + S3 wiki pages.  Returns structured JSON for AgentCore agents.
"""

import json
import os
import re
import boto3
from datetime import datetime, timezone

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime",
                       region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime",
                                     region_name=os.environ.get("AWS_REGION", "us-east-1"))
ssm = boto3.client("ssm")
dynamodb = boto3.resource("dynamodb")

WIKI_BUCKET  = os.environ["WIKI_BUCKET"]
MODEL_ID     = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
KB_ID_PARAM  = os.environ.get("KB_ID_PARAM", "/llmwiki/bedrock_kb_id")
INDEX_TABLE  = os.environ.get("DYNAMODB_INDEX", "llmwiki-index")

UC_TITLES = {
    "UC1":  "Sales to Service — Customer Onboarding",
    "UC2":  "Environment Provisioning",
    "UC3":  "Identity and Access Onboarding",
    "UC4":  "Business Configuration",
    "UC5":  "Data Migration",
    "UC6":  "System Integration Testing",
    "UC7":  "End-to-End Testing",
    "UC8":  "Cutover Planning and Execution",
    "UC9":  "Operational Readiness and Handover",
    "UC10": "Hypercare and Early Run Stabilization",
}

_kb_id_cache = None


# ── Entry point ────────────────────────────────────────────────────

def lambda_handler(event, context):
    http_method = event.get("httpMethod", "GET")
    path        = event.get("path", "")
    params      = event.get("pathParameters") or event.get("queryStringParameters") or {}

    # GET /wiki/playbook/{use_case}
    m = re.search(r"/wiki/playbook/([^/]+)$", path)
    if m:
        uc = (m.group(1) or params.get("use_case", "")).upper()
        return respond(200, get_playbook(uc))

    # GET /wiki/customer/{customer_id}
    m = re.search(r"/wiki/customer/([^/]+)$", path)
    if m:
        cid = m.group(1) or params.get("customer_id", "")
        return respond(200, get_customer_context(cid))

    # GET /wiki/artifact/{artifact_type}
    m = re.search(r"/wiki/artifact/([^/]+)$", path)
    if m:
        atype = m.group(1) or params.get("artifact_type", "")
        return respond(200, get_artifact(atype))

    # Direct invocation (Streamlit / tests)
    body = event if "action" in event else {}
    action = body.get("action", "")
    if action == "get_playbook":
        return respond(200, get_playbook(body.get("use_case", "UC1").upper()))
    if action == "get_customer":
        return respond(200, get_customer_context(body.get("customer_id", "")))
    if action == "get_artifact":
        return respond(200, get_artifact(body.get("artifact_type", "")))

    return respond(400, {"error": "Unrecognised route. Use /wiki/playbook/{uc}, /wiki/customer/{id}, or /wiki/artifact/{type}"})


# ── Playbook assembly ──────────────────────────────────────────────

def get_playbook(use_case: str) -> dict:
    if not use_case:
        return {"error": "use_case required (UC1–UC10)"}

    title = UC_TITLES.get(use_case, f"{use_case} Playbook")

    # Retrieve wiki pages tagged for this use case
    pages = _scan_pages_for_uc(use_case)
    page_contents = _read_pages(pages[:8])   # cap at 8 pages for context

    if not page_contents:
        return {
            "use_case":      use_case,
            "title":         title,
            "current_as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "steps":         [],
            "required_artifacts": [],
            "decision_gates":     [],
            "evidence_required":  [],
            "note": "No wiki pages tagged for this use case yet. Ingest relevant documents first.",
        }

    context_str = "\n\n---\n\n".join(page_contents[:6000])

    prompt = f"""Assemble a step-by-step implementation playbook for {use_case}: {title}.
Use ONLY the wiki content below. Return a JSON object with these exact keys:
{{
  "steps": [
    {{"step": 1, "title": "Step title", "description": "What to do",
      "action_items": ["action 1"], "wiki_page": "page-slug-if-known"}}
  ],
  "required_artifacts": [{{"name": "artifact name", "wiki_key": "wiki/artifacts/slug.md"}}],
  "decision_gates": ["G0", "G1"],
  "evidence_required": ["evidence item 1"]
}}

WIKI CONTENT:
{context_str}

Return ONLY valid JSON. Include 3-7 steps. If information is missing, note it in the step description."""

    try:
        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 1500},
        }
        resp = bedrock.converse(**_converse_kwargs)
        raw  = resp["output"]["message"]["content"][0]["text"].strip()
        m    = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    except Exception as e:
        print(f"Playbook synthesis failed: {e}")
        data = {}

    return {
        "use_case":          use_case,
        "title":             title,
        "current_as_of":     datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "steps":             data.get("steps", []),
        "required_artifacts":data.get("required_artifacts", []),
        "decision_gates":    data.get("decision_gates", []),
        "evidence_required": data.get("evidence_required", []),
        "source_page_count": len(pages),
    }


# ── Customer context ───────────────────────────────────────────────

def get_customer_context(customer_id: str) -> dict:
    if not customer_id:
        return {"error": "customer_id required"}

    cid_slug = re.sub(r"[^a-z0-9-]", "-", customer_id.lower()).strip("-")

    # Collect all pages for this customer
    pages, contents = [], []
    for page_type in ("customers", "decisions", "evidence", "sources"):
        items = _query_index_by_type(page_type)
        for item in items:
            slug = item.get("page_slug", "")
            cid_match = (item.get("customer_id", "") == customer_id
                         or cid_slug in slug)
            if cid_match:
                pages.append(item)
                try:
                    obj = s3.get_object(Bucket=WIKI_BUCKET, Key=item["s3_key"])
                    contents.append(obj["Body"].read().decode("utf-8")[:2000])
                except Exception:
                    pass

    if not pages:
        return {
            "customer_id":    customer_id,
            "status":         "no-history",
            "overview":       "No prior history for this customer in the wiki.",
            "pages_found":    0,
            "key_facts":      [],
            "active_projects":[],
            "products_in_scope": [],
            "open_decisions": [],
            "related_pages":  [],
        }

    # Synthesize with Claude
    context_str = "\n\n---\n\n".join(contents[:4000])
    prompt = f"""Synthesize everything the wiki knows about customer {customer_id}.
Return a JSON object:
{{
  "overview": "1-2 paragraph customer overview",
  "key_facts": ["fact 1", "fact 2"],
  "products_in_scope": ["Product A"],
  "active_projects": ["project name"],
  "open_decisions": ["decision pending"],
  "last_updated": "YYYY-MM-DD"
}}
WIKI CONTENT:
{context_str}
Return ONLY valid JSON."""

    try:
        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 800},
        }
        resp = bedrock.converse(**_converse_kwargs)
        raw  = resp["output"]["message"]["content"][0]["text"].strip()
        m    = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    except Exception as e:
        print(f"Customer synthesis failed: {e}")
        data = {}

    return {
        "customer_id":       customer_id,
        "status":            "found",
        "overview":          data.get("overview", ""),
        "key_facts":         data.get("key_facts", []),
        "products_in_scope": data.get("products_in_scope", []),
        "active_projects":   data.get("active_projects", []),
        "open_decisions":    data.get("open_decisions", []),
        "last_updated":      data.get("last_updated", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "pages_found":       len(pages),
        "related_pages":     [p.get("s3_key", "") for p in pages],
    }


# ── Artifact retrieval ─────────────────────────────────────────────

def get_artifact(artifact_type: str) -> dict:
    if not artifact_type:
        return {"error": "artifact_type required"}

    slug = re.sub(r"[^a-z0-9-]", "-", artifact_type.lower()).strip("-")

    # Search artifacts/ prefix
    for candidate_key in [
        f"wiki/artifacts/{slug}.md",
        f"wiki/runbooks/{slug}.md",
        f"wiki/sops/{slug}.md",
    ]:
        try:
            obj     = s3.get_object(Bucket=WIKI_BUCKET, Key=candidate_key)
            content = obj["Body"].read().decode("utf-8")
            return {
                "artifact_type": artifact_type,
                "s3_key":        candidate_key,
                "s3_uri":        f"s3://{WIKI_BUCKET}/{candidate_key}",
                "content":       content,
                "found":         True,
            }
        except Exception:
            continue

    # Fuzzy search in index
    items = _query_index_by_type("artifacts") + _query_index_by_type("runbooks")
    for item in items:
        if slug in item.get("page_slug", ""):
            key = item.get("s3_key", "")
            try:
                obj     = s3.get_object(Bucket=WIKI_BUCKET, Key=key)
                content = obj["Body"].read().decode("utf-8")
                return {
                    "artifact_type": artifact_type,
                    "s3_key":        key,
                    "s3_uri":        f"s3://{WIKI_BUCKET}/{key}",
                    "content":       content,
                    "found":         True,
                }
            except Exception:
                pass

    return {
        "artifact_type": artifact_type,
        "found":         False,
        "note": f"No artifact '{artifact_type}' found. Ingest the source document containing this template.",
    }


# ── DynamoDB helpers ───────────────────────────────────────────────

def _scan_pages_for_uc(use_case: str) -> list:
    results = []
    for page_type in ("runbooks", "sops", "artifacts", "decisions", "sources", "concepts"):
        items = _query_index_by_type(page_type)
        for item in items:
            uc_tags = item.get("use_case", "") or item.get("use_case_tags", "")
            if use_case.lower() in str(uc_tags).lower() or page_type in ("runbooks", "sops"):
                results.append(item)
    return results


def _query_index_by_type(page_type: str) -> list:
    try:
        table = dynamodb.Table(INDEX_TABLE)
        resp  = table.query(
            KeyConditionExpression="page_type = :pt",
            ExpressionAttributeValues={":pt": page_type},
        )
        return resp.get("Items", [])
    except Exception:
        return []


def _read_pages(items: list) -> list:
    contents = []
    for item in items:
        key = item.get("s3_key", "")
        if not key:
            continue
        try:
            obj = s3.get_object(Bucket=WIKI_BUCKET, Key=key)
            contents.append(obj["Body"].read().decode("utf-8")[:1500])
        except Exception:
            pass
    return contents


def respond(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
