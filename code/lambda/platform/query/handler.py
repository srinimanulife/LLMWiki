"""
Query Lambda — answers natural language questions against the LLMWiki.
Called by API Gateway (POST /query, GET /wiki/status, GET /wiki/gaps)
and by the Streamlit UI directly.
Uses Bedrock Knowledge Base for retrieval + Claude for synthesis.
On low-confidence answers, identifies knowledge gaps and creates stub pages.
"""

import json
import os
import uuid
import boto3
from datetime import datetime, timezone

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
ssm = boto3.client("ssm")
dynamodb = boto3.resource("dynamodb")

WIKI_BUCKET = os.environ["WIKI_BUCKET"]
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
KB_ID_PARAM = os.environ.get("KB_ID_PARAM", "/llmwiki/bedrock_kb_id")
INDEX_TABLE = os.environ.get("DYNAMODB_INDEX", "llmwiki-index")
REGISTRY_TABLE = os.environ.get("REGISTRY_TABLE", "llmwiki-source-registry")
GAPS_TABLE = os.environ.get("GAPS_TABLE", "")

_kb_id_cache = None


def lambda_handler(event, context):
    # Route GET /wiki/status from API Gateway before touching body
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")
    if http_method == "GET" and path.endswith("/status"):
        return respond(200, get_wiki_status())
    if http_method == "GET" and path.endswith("/gaps"):
        return respond(200, list_gaps())

    # Support direct invocation (from Streamlit) and API Gateway POST
    raw_body = event.get("body") if "body" in event else None
    if raw_body is not None:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    else:
        body = event

    action = body.get("action", "query")

    if action == "status":
        return respond(200, get_wiki_status())

    if action == "get_page":
        page_key = body.get("page_key", "")
        return respond(200, get_wiki_page(page_key))

    if action == "list_pages":
        page_type = body.get("page_type", "")
        return respond(200, list_pages(page_type))

    if action == "get_gaps":
        status_filter = body.get("status_filter")
        limit = int(body.get("limit", 50))
        return respond(200, list_gaps(status_filter, limit))

    if action == "create_stub":
        gap_slug = body.get("gap_slug", "")
        gap_title = body.get("gap_title", gap_slug.replace("-", " ").title())
        gap_type = body.get("gap_type", "question")
        if not gap_slug:
            return respond(400, {"error": "Missing gap_slug"})
        gap = {"slug": gap_slug, "title": gap_title, "type": gap_type}
        create_stub_page(gap)
        return respond(200, {"status": "created", "slug": gap_slug})

    if action == "dismiss_gap":
        gap_id = body.get("gap_id", "")
        if gap_id and GAPS_TABLE:
            dynamodb.Table(GAPS_TABLE).update_item(
                Key={"gap_id": gap_id},
                UpdateExpression="SET #st = :d",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":d": "dismissed"},
            )
        return respond(200, {"status": "dismissed"})

    # Default: search/query
    question = body.get("q", body.get("question", "")).strip()
    if not question:
        return respond(400, {"error": "Missing 'q' field in request body"})

    result = answer_question(question)
    return respond(200, result)


def answer_question(question: str) -> dict:
    """Retrieve relevant wiki pages and synthesize a cited answer."""
    kb_id = get_kb_id()

    if not kb_id:
        return fallback_answer(question)

    # Retrieve from Knowledge Base
    try:
        retrieve_response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": question},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": 5,
                    "overrideSearchType": "SEMANTIC"
                }
            },
        )
        results = retrieve_response.get("retrievalResults", [])
    except Exception as e:
        print(f"KB retrieval failed: {e}. Falling back.")
        return fallback_answer(question)

    if not results:
        gaps_identified = identify_and_record_gaps(question, "")
        return {
            "answer": "The wiki does not yet have information about this topic. Try ingesting relevant documents first.",
            "sources": [],
            "confidence": "low",
            "gaps_identified": gaps_identified,
        }

    # Build context from retrieved passages
    context_parts = []
    sources = []
    for r in results:
        text = r["content"]["text"]
        location = r.get("location", {}).get("s3Location", {})
        uri = location.get("uri", "unknown")
        score = r.get("score", 0)
        context_parts.append(f"[Source: {uri}]\n{text}")
        sources.append({
            "s3_uri": uri,
            "page_slug": uri.split("/")[-1].replace(".md", "") if uri != "unknown" else "unknown",
            "relevance_score": round(score, 3),
        })

    context = "\n\n---\n\n".join(context_parts)

    # Synthesize answer
    synthesis_prompt = f"""You are answering questions using a knowledge wiki. Use ONLY the wiki content provided below.
Cite sources by referencing their wiki page slug in [[double brackets]].
If the wiki content is insufficient to answer, say so clearly.

QUESTION: {question}

WIKI CONTENT:
{context}

Provide a clear, concise answer with citations. Format key points as bullet points if there are multiple."""

    _converse_kwargs = {
        "modelId": MODEL_ID,
        "messages": [{"role": "user", "content": [{"text": synthesis_prompt}]}],
        "inferenceConfig": {"maxTokens": 1024},
    }
    response = bedrock.converse(**_converse_kwargs)
    answer = response["output"]["message"]["content"][0]["text"].strip()

    confidence = "high" if len(results) >= 3 else "medium" if len(results) >= 1 else "low"

    # Enrich sources with provenance (original upload path → download link)
    for src in sources:
        slug = src.get("page_slug", "")
        if slug and slug != "unknown":
            src["provenance"] = get_page_provenance(slug)

    # Detect knowledge gaps on low/medium confidence answers
    gaps_identified = []
    if confidence in ("low", "medium"):
        gaps_identified = identify_and_record_gaps(question, context)

    return {
        "answer": answer,
        "sources": sources[:5],
        "confidence": confidence,
        "kb_results_count": len(results),
        "gaps_identified": gaps_identified,
    }


def get_page_provenance(page_slug: str) -> dict:
    """Look up provenance (original upload chain) for a wiki source page."""
    try:
        table = dynamodb.Table(INDEX_TABLE)
        resp = table.get_item(Key={"page_type": "sources", "page_slug": page_slug})
        raw = resp.get("Item", {}).get("source_provenance", "")
        if raw:
            return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass

    # Fallback: check registry directly
    try:
        table = dynamodb.Table(REGISTRY_TABLE)
        resp = table.get_item(Key={"source_id": page_slug})
        item = resp.get("Item", {})
        if item:
            orig = item.get("original_upload_key", "")
            return {
                "original_file": orig,
                "original_s3_uri": f"s3://{WIKI_BUCKET}/{orig}" if orig else "",
                "raw_markdown": item.get("converted_key", ""),
                "raw_assets": item.get("raw_assets_key", ""),
            }
    except Exception:
        pass

    return {}


def identify_and_record_gaps(question: str, context: str) -> list:
    """Ask Claude to identify knowledge gaps, record them, and create stub pages."""
    if not GAPS_TABLE:
        return []
    try:
        coverage_note = "The wiki returned no relevant results." if not context else "The wiki returned partial results with medium/low confidence."
        gap_prompt = f"""A user asked a question that the wiki could not answer well.
{coverage_note}

QUESTION: {question}

Identify 2-3 specific knowledge gaps — topics, entities, or concepts that should be documented in the wiki to answer this question.

Return ONLY a JSON array with no explanation:
[
  {{"type": "entity|concept|question", "title": "Human Readable Title", "slug": "kebab-case-slug", "rationale": "One sentence why this is needed."}}
]"""

        _converse_kwargs = {
            "modelId": MODEL_ID,
            "messages": [{"role": "user", "content": [{"text": gap_prompt}]}],
            "inferenceConfig": {"maxTokens": 256},
        }
        response = bedrock.converse(**_converse_kwargs)
        raw = response["output"]["message"]["content"][0]["text"].strip()

        import re
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            return []

        gaps = json.loads(match.group())
        recorded = []
        for gap in gaps[:3]:
            if not gap.get("slug"):
                continue
            record_gap(gap, question)
            recorded.append({"type": gap.get("type"), "title": gap.get("title"), "slug": gap.get("slug")})
        return recorded
    except Exception as e:
        print(f"WARN: Gap analysis failed (non-fatal): {e}")
        return []


def record_gap(gap: dict, source_query: str):
    """Insert or increment a gap record in DynamoDB, then create a stub page."""
    if not GAPS_TABLE:
        return
    try:
        table = dynamodb.Table(GAPS_TABLE)
        slug = gap["slug"]
        now = datetime.now(timezone.utc).isoformat()

        # Check if gap already exists via slug GSI
        existing = table.query(
            IndexName="slug_index",
            KeyConditionExpression="gap_slug = :s",
            ExpressionAttributeValues={":s": slug},
            Limit=1,
        ).get("Items", [])

        if existing:
            # Increment priority for repeated queries on the same gap
            table.update_item(
                Key={"gap_id": existing[0]["gap_id"]},
                UpdateExpression="ADD priority_score :one SET last_seen_at = :t",
                ExpressionAttributeValues={":one": 1, ":t": now},
            )
        else:
            table.put_item(Item={
                "gap_id": str(uuid.uuid4()),
                "gap_slug": slug,
                "gap_type": gap.get("type", "question"),
                "gap_title": gap.get("title", slug.replace("-", " ").title()),
                "gap_rationale": gap.get("rationale", ""),
                "source_query": source_query[:200],
                "priority_score": 1,
                "status": "suggested",
                "created_at": now,
            })
            # Auto-create a stub page for brand-new gaps
            create_stub_page(gap)
    except Exception as e:
        print(f"WARN: Could not record gap {gap.get('slug')}: {e}")


def create_stub_page(gap: dict):
    """Write a minimal stub wiki page for a knowledge gap."""
    slug = gap["slug"]
    title = gap.get("title", slug.replace("-", " ").title())
    gap_type = gap.get("type", "question")
    s3_key = f"wiki/questions/{slug}.md"

    # Don't overwrite an existing real page
    try:
        s3.head_object(Bucket=WIKI_BUCKET, Key=s3_key)
        return
    except Exception:
        pass

    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rationale = gap.get("rationale", "")
    content = f"""---
title: {title}
date: {now_date}
tags: [stub, {gap_type}, knowledge-gap]
status: stub
gap_type: {gap_type}
---

# {title}

> **Knowledge Gap** — This stub was auto-created because a user query revealed this topic is not yet documented in the wiki.
> To fill this gap, upload relevant documents via the Upload Documents page.

## Why This Page Was Created

{rationale or f"A user asked a question that required knowledge about {title}, but no wiki pages covered this topic."}

## What Should Go Here

- Definition and overview of {title}
- Key facts, metrics, or decisions related to this topic
- Links to related wiki pages and source documents

## Related Pages

*(To be populated when source documents are ingested)*
"""
    s3.put_object(
        Bucket=WIKI_BUCKET,
        Key=s3_key,
        Body=content.encode("utf-8"),
        ContentType="text/markdown",
    )

    # Register stub in the DynamoDB index
    now = datetime.now(timezone.utc).isoformat()
    dynamodb.Table(INDEX_TABLE).put_item(Item={
        "page_type": "questions",
        "page_slug": slug,
        "s3_key": s3_key,
        "last_updated": now,
        "source_type": "gap",
        "status": "stub",
    })
    print(f"  Stub created: {s3_key}")


def list_gaps(status_filter: str = None, limit: int = 50) -> dict:
    """Return knowledge gaps, optionally filtered by status."""
    if not GAPS_TABLE:
        return {"gaps": [], "error": "Gaps table not configured"}
    try:
        table = dynamodb.Table(GAPS_TABLE)
        if status_filter:
            resp = table.query(
                IndexName="status_index",
                KeyConditionExpression="#st = :s",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":s": status_filter},
                Limit=limit,
                ScanIndexForward=False,
            )
        else:
            resp = table.scan(Limit=limit)
        items = resp.get("Items", [])
        # Sort by priority_score descending
        items.sort(key=lambda x: int(x.get("priority_score", 0)), reverse=True)
        return {"gaps": items, "count": len(items)}
    except Exception as e:
        return {"gaps": [], "error": str(e)}


def fallback_answer(question: str) -> dict:
    """Answer by reading wiki/index.md + overview.md when KB is unavailable."""
    wiki_context = ""
    try:
        idx = s3.get_object(Bucket=WIKI_BUCKET, Key="wiki/index.md")
        wiki_context += idx["Body"].read().decode("utf-8")[:3000]
    except Exception:
        pass

    try:
        ov = s3.get_object(Bucket=WIKI_BUCKET, Key="wiki/overview.md")
        wiki_context += "\n\n" + ov["Body"].read().decode("utf-8")[:3000]
    except Exception:
        pass

    if not wiki_context:
        return {
            "answer": "Wiki is empty. Upload documents to raw/ to begin building the knowledge base.",
            "sources": [],
            "confidence": "low",
            "gaps_identified": [],
        }

    prompt = f"""Answer this question using the wiki index and overview:

QUESTION: {question}

WIKI CONTENT:
{wiki_context}

Provide a concise answer. If the wiki doesn't contain the answer, say so."""

    _converse_kwargs = {
        "modelId": MODEL_ID,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 512},
    }
    response = bedrock.converse(**_converse_kwargs)
    return {
        "answer": response["output"]["message"]["content"][0]["text"].strip(),
        "sources": [],
        "confidence": "low",
        "note": "KB unavailable — answered from index only",
        "gaps_identified": [],
    }


def get_wiki_status() -> dict:
    """Return a summary of current wiki health including gap counts."""
    table = dynamodb.Table(INDEX_TABLE)
    counts = {}
    try:
        response = table.scan(ProjectionExpression="page_type")
        for item in response.get("Items", []):
            pt = item.get("page_type", "unknown")
            counts[pt] = counts.get(pt, 0) + 1
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ProjectionExpression="page_type",
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            for item in response.get("Items", []):
                pt = item.get("page_type", "unknown")
                counts[pt] = counts.get(pt, 0) + 1
    except Exception as e:
        print(f"DynamoDB scan error: {e}")

    total = sum(counts.values())

    # Gap counts
    gap_counts = {}
    try:
        if GAPS_TABLE:
            gap_resp = dynamodb.Table(GAPS_TABLE).scan(ProjectionExpression="#st", ExpressionAttributeNames={"#st": "status"})
            for item in gap_resp.get("Items", []):
                st = item.get("status", "unknown")
                gap_counts[st] = gap_counts.get(st, 0) + 1
    except Exception:
        pass

    return {
        "status": "ok",
        "total_pages": total,
        "pages_by_type": counts,
        "wiki_bucket": WIKI_BUCKET,
        "model": MODEL_ID,
        "gaps_by_status": gap_counts,
    }


def get_wiki_page(page_key: str) -> dict:
    """Read and return a specific wiki page from S3."""
    if not page_key.startswith("wiki/"):
        page_key = f"wiki/{page_key}"
    if not page_key.endswith(".md"):
        page_key = f"{page_key}.md"
    try:
        response = s3.get_object(Bucket=WIKI_BUCKET, Key=page_key)
        content = response["Body"].read().decode("utf-8")
        return {"page_key": page_key, "content": content}
    except s3.exceptions.NoSuchKey:
        return {"error": f"Page not found: {page_key}"}


def list_pages(page_type: str = "") -> dict:
    """List wiki pages, optionally filtered by type."""
    table = dynamodb.Table(INDEX_TABLE)
    try:
        if page_type:
            response = table.query(
                KeyConditionExpression="page_type = :pt",
                ExpressionAttributeValues={":pt": page_type}
            )
        else:
            response = table.scan()
        items = response.get("Items", [])
        return {"pages": items, "count": len(items)}
    except Exception as e:
        return {"error": str(e), "pages": []}


def get_kb_id() -> str:
    global _kb_id_cache
    if _kb_id_cache:
        return _kb_id_cache
    try:
        response = ssm.get_parameter(Name=KB_ID_PARAM)
        _kb_id_cache = response["Parameter"]["Value"]
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
