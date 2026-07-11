"""
Business Query Lambda — POST /wiki/ask, POST /wiki/query/{domain}
Returns structured JSON (answer + confidence + action_items + artifacts_referenced
+ gaps_detected) for AgentCore sub-agents.  Wraps the existing KB retrieve +
Claude synthesis pipeline from query/handler.py and adds domain routing,
intent detection, and a structured response builder.
"""

import json
import os
import re
import sys
import boto3
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
try:
    from governance import record_usage, cache_get, cache_put, check_rate_limit, check_budget_ceiling
    _GOVERNANCE = True
except ImportError:
    _GOVERNANCE = False
    print("WARN: governance module not found — cost tracking/rate limiting disabled")

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime",
                       region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime",
                                     region_name=os.environ.get("AWS_REGION", "us-east-1"))
ssm = boto3.client("ssm")
dynamodb = boto3.resource("dynamodb")

WIKI_BUCKET      = os.environ["WIKI_BUCKET"]
MODEL_ID         = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
KB_ID_PARAM      = os.environ.get("KB_ID_PARAM", "/llmwiki/bedrock_kb_id")
INDEX_TABLE      = os.environ.get("DYNAMODB_INDEX", "llmwiki-index")
GAPS_TABLE       = os.environ.get("GAPS_TABLE", "llmwiki-gaps")
CONTRIB_TABLE    = os.environ.get("CONTRIB_TABLE", "llmwiki-contributions")

VALID_DOMAINS = {
    "customer-onboarding", "provisioning", "identity-access",
    "configuration", "data-migration", "testing",
    "cutover", "handover", "hypercare",
}

_kb_id_cache = None


# ── Entry point ────────────────────────────────────────────────────

def lambda_handler(event, context):
    http_method = event.get("httpMethod", "POST")
    path        = event.get("path", "/wiki/ask")

    # Support direct dict invocation (tests / Streamlit)
    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    # Extract domain from path  /wiki/query/{domain}
    domain_from_path = None
    m = re.search(r"/wiki/query/([^/]+)$", path)
    if m:
        domain_from_path = m.group(1)

    domain = domain_from_path or body.get("domain", "")
    question = body.get("question", body.get("q", "")).strip()

    if not question:
        return respond(400, {"error": "Missing 'question' field"})

    # ── Rate limiting + budget ceiling (AgentCore callers) ─────────
    caller = body.get("agent_id", body.get("caller",
             event.get("requestContext", {}).get("identity", {}).get("sourceIp", "agentcore")))
    if _GOVERNANCE:
        allowed, rate_info = check_rate_limit(caller, window_minutes=1, max_requests=30)
        if not allowed:
            return respond(429, {"error": "Rate limit exceeded", "detail": rate_info})
        if not check_budget_ceiling(caller, daily_limit_usd=5.0):
            return respond(429, {"error": "Daily cost ceiling reached",
                                 "detail": {"caller": caller}})

    context_meta = body.get("context", {})
    customer_id   = body.get("customer_id", context_meta.get("customer_id", ""))
    use_case      = body.get("use_case", context_meta.get("use_case", ""))
    max_results   = int(body.get("max_results", 5))
    include_items = body.get("include_action_items", True)

    result = answer_business_question(
        question=question,
        domain=domain,
        customer_id=customer_id,
        use_case=use_case,
        max_results=max_results,
        include_action_items=include_items,
        caller=caller,
    )
    return respond(200, result)


# ── Core business query ────────────────────────────────────────────

def answer_business_question(
    question: str,
    domain: str = "",
    customer_id: str = "",
    use_case: str = "",
    max_results: int = 5,
    include_action_items: bool = True,
    caller: str = "agentcore",
) -> dict:

    kb_id = get_kb_id()
    intent = detect_intent(question)

    # Build KB retrieval filter when domain is known
    retrieval_cfg = {
        "vectorSearchConfiguration": {
            "numberOfResults": max_results,
            "overrideSearchType": "SEMANTIC",
        }
    }
    if domain and domain in VALID_DOMAINS:
        retrieval_cfg["vectorSearchConfiguration"]["filter"] = {
            "orAll": [
                {"equals": {"key": "domain",        "value": domain}},
                {"equals": {"key": "use_case_tags", "value": use_case or "UC1"}},
            ]
        }

    # Augment question with customer context
    retrieval_question = question
    if customer_id:
        retrieval_question = f"[Customer: {customer_id}] {question}"
    if use_case:
        retrieval_question = f"[UseCase: {use_case}] {retrieval_question}"

    try:
        retrieve_resp = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": retrieval_question},
            retrievalConfiguration=retrieval_cfg,
        )
        results = retrieve_resp.get("retrievalResults", [])
    except Exception as e:
        print(f"KB retrieve failed: {e}")
        results = []

    # Fall back to unfiltered retrieval when domain filter yields nothing
    if not results and domain and domain in VALID_DOMAINS:
        try:
            fallback_cfg = {"vectorSearchConfiguration": {"numberOfResults": max_results, "overrideSearchType": "SEMANTIC"}}
            retrieve_resp = bedrock_agent_runtime.retrieve(
                knowledgeBaseId=kb_id,
                retrievalQuery={"text": retrieval_question},
                retrievalConfiguration=fallback_cfg,
            )
            results = retrieve_resp.get("retrievalResults", [])
        except Exception as e:
            print(f"KB fallback retrieve failed: {e}")

    if not results:
        gaps = _detect_gaps(question, domain, use_case)
        return {
            "answer": "The wiki does not yet have information about this topic. "
                      "Ingest relevant documents via raw/ to build coverage.",
            "confidence":           "low",
            "domain":               domain,
            "use_case_tags":        [use_case] if use_case else [],
            "sources":              [],
            "action_items":         [],
            "artifacts_referenced": [],
            "evidence_required":    [],
            "gaps_detected":        gaps,
            "wiki_page_count":      0,
            "contributing_agent_hint": None,
        }

    # Build context string
    context_parts, sources = [], []
    for r in results:
        text     = r["content"]["text"]
        loc      = r.get("location", {}).get("s3Location", {})
        uri      = loc.get("uri", "unknown")
        score    = round(r.get("score", 0), 3)
        slug     = uri.split("/")[-1].replace(".md", "") if uri != "unknown" else "unknown"
        page_type = _page_type_from_uri(uri)
        context_parts.append(f"[{uri}]\n{text}")
        sources.append({
            "page_slug":       slug,
            "page_type":       page_type,
            "s3_uri":          uri,
            "relevance_score": score,
            "excerpt":         text[:300].replace("\n", " "),
            "artifact_type":   _artifact_type_from_slug(slug),
            "decision_gate":   _gate_from_slug(slug),
        })

    context_str = "\n\n---\n\n".join(context_parts)

    # Synthesis prompt — structured output
    synthesis_prompt = f"""You are the LLMWiki Business Knowledge API. Answer the agent's question using ONLY the wiki content provided below.

QUESTION: {question}
DOMAIN: {domain or "general"}
USE CASE: {use_case or "not specified"}
CUSTOMER: {customer_id or "not specified"}
INTENT: {intent}

WIKI CONTENT:
{context_str[:6000]}

Respond with a JSON object containing these exact keys:
{{
  "answer": "Clear synthesized answer in plain language. Cite sources using [[page-slug]] notation.",
  "confidence": "high|medium|low",
  "action_items": ["concrete action 1", "concrete action 2"],
  "artifacts_referenced": [{{"name": "template name", "s3_key": "wiki/artifacts/slug.md"}}],
  "evidence_required": ["evidence item 1"],
  "contributing_agent_hint": "null or suggestion for what the agent should contribute back"
}}

Rules:
- confidence = high if 3+ strong sources; medium if 1-2 sources; low if sources are tangential
- action_items: list ONLY concrete, implementable actions — not observations
- artifacts_referenced: only list templates/checklists/runbooks explicitly mentioned in sources
- evidence_required: compliance evidence items this answer references (empty list if none)
- contributing_agent_hint: if the agent should write something back to the wiki, say what
- Do NOT invent facts not present in the wiki content
- Return ONLY valid JSON, no preamble"""

    try:
        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": synthesis_prompt}]}],
            "inferenceConfig": {"maxTokens": 1024},
        }
        resp = bedrock.converse(**_converse_kwargs)
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        # ── Cost tracking ──────────────────────────────────────────
        if _GOVERNANCE:
            usage = resp.get("usage", {})
            record_usage(
                MODEL_ID,
                usage.get("inputTokens", 0),
                usage.get("outputTokens", 0),
                caller=caller,
                operation="business_ask",
            )
        # Extract JSON block
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        synthesis = json.loads(m.group()) if m else {}
    except Exception as e:
        print(f"Synthesis failed: {e}")
        synthesis = {"answer": context_parts[0][:500] if context_parts else "No answer.", "confidence": "low"}

    confidence = synthesis.get("confidence", "medium")
    gaps = _detect_gaps(question, domain, use_case) if confidence in ("low", "medium") else []

    result = {
        "answer":                synthesis.get("answer", ""),
        "confidence":            confidence,
        "domain":                domain,
        "use_case_tags":         [use_case] if use_case else [],
        "sources":               sources,
        "action_items":          synthesis.get("action_items", []) if include_action_items else [],
        "artifacts_referenced":  synthesis.get("artifacts_referenced", []),
        "evidence_required":     synthesis.get("evidence_required", []),
        "gaps_detected":         gaps,
        "wiki_page_count":       len(sources),
        "contributing_agent_hint": synthesis.get("contributing_agent_hint"),
    }
    return result


# ── Intent detection ───────────────────────────────────────────────

def detect_intent(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["checklist", "steps", "procedure", "how to", "process"]):
        return "retrieve-checklist"
    if any(w in q for w in ["template", "artifact", "document", "form", "bom"]):
        return "retrieve-artifact"
    if any(w in q for w in ["who", "what is", "define", "contact", "person", "team"]):
        return "retrieve-entity"
    return "retrieve-narrative"


# ── Gap detection ──────────────────────────────────────────────────

def _detect_gaps(question: str, domain: str, use_case: str) -> list:
    if not GAPS_TABLE:
        return []
    try:
        prompt = f"""A business agent asked a question the wiki could not answer confidently.
QUESTION: {question}
DOMAIN: {domain}
USE CASE: {use_case}

Identify 1-3 specific knowledge gaps. Return ONLY a JSON array:
[{{"type":"entity|concept|question","slug":"kebab-case","title":"Human Title"}}]"""
        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 256},
        }
        resp = bedrock.converse(**_converse_kwargs)
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        return json.loads(m.group())[:3] if m else []
    except Exception as e:
        print(f"WARN: gap detection failed: {e}")
        return []


# ── Helpers ────────────────────────────────────────────────────────

def _page_type_from_uri(uri: str) -> str:
    parts = uri.split("/")
    if len(parts) >= 2:
        return parts[-2]
    return "sources"


def _artifact_type_from_slug(slug: str) -> str | None:
    for kw in ["template", "checklist", "runbook", "bom", "sop", "playbook"]:
        if kw in slug:
            return kw
    return None


def _gate_from_slug(slug: str) -> str | None:
    m = re.search(r'\bG[0-6]\b', slug, re.IGNORECASE)
    return m.group().upper() if m else None


def get_kb_id() -> str:
    global _kb_id_cache
    if _kb_id_cache:
        return _kb_id_cache
    try:
        _kb_id_cache = ssm.get_parameter(Name=KB_ID_PARAM)["Parameter"]["Value"]
        return _kb_id_cache
    except Exception:
        return ""


def respond(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
