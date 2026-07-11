"""
Ingest Lambda — triggered by S3 ObjectCreated on raw/*.md
Reads the source, calls Bedrock Claude to generate wiki pages,
writes them to wiki/ in S3, and updates DynamoDB index + log.
"""

import json
import os
import re
import boto3
import urllib.parse
from datetime import datetime, timezone

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")

WIKI_BUCKET = os.environ["WIKI_BUCKET"]
INDEX_TABLE = os.environ["DYNAMODB_INDEX_TABLE"]
LOG_TABLE = os.environ["DYNAMODB_LOG_TABLE"]
REGISTRY_TABLE = os.environ["DYNAMODB_REGISTRY"]
GAPS_TABLE = os.environ.get("GAPS_TABLE", "")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
KB_ID_PARAM = os.environ.get("KB_ID_PARAM", "/llmwiki/bedrock_kb_id")
KB_DS_PARAM = os.environ.get("KB_DS_ID_PARAM", "/llmwiki/bedrock_kb_datasource_id")


def lambda_handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        print(f"Processing: s3://{bucket}/{key}")

        try:
            process_source(bucket, key)
        except Exception as e:
            print(f"ERROR processing {key}: {e}")
            raise

    # Trigger KB sync after processing
    try:
        sync_knowledge_base()
    except Exception as e:
        print(f"WARN: KB sync failed (non-fatal): {e}")

    return {"statusCode": 200, "body": "Ingest complete"}


def process_source(bucket: str, key: str):
    # Skip if already processed
    slug = key_to_slug(key)
    if is_already_processed(slug):
        print(f"Skipping {slug} — already has a wiki page")
        return

    # Read source content
    response = s3.get_object(Bucket=bucket, Key=key)
    source_text = response["Body"].read().decode("utf-8")

    if len(source_text.strip()) < 50:
        print(f"Skipping {key} — too short ({len(source_text)} chars)")
        return

    source_type = infer_source_type(key)

    # Look up original upload provenance from registry
    provenance = get_source_provenance(slug, key)

    # Generate wiki pages via Bedrock
    wiki_pages = generate_wiki_pages(source_text, slug, source_type, key, provenance)

    # Write pages to S3
    now = datetime.now(timezone.utc).isoformat()
    pages_created = []

    for page_type, page_slug, content in wiki_pages:
        s3_key = f"wiki/{page_type}/{page_slug}.md"
        s3.put_object(
            Bucket=WIKI_BUCKET,
            Key=s3_key,
            Body=content.encode("utf-8"),
            ContentType="text/markdown",
        )
        print(f"  Written: {s3_key}")

        update_wiki_index(page_type, page_slug, s3_key, now, source_type, provenance)
        pages_created.append(f"{page_type}/{page_slug}")

    # Append to log
    append_log(key, slug, pages_created, now)

    # Mark processed in source registry (preserves original provenance fields)
    mark_processed(slug, key, pages_created, now, provenance)

    # Resolve any gaps this document closes
    resolve_gaps_for_slug(slug, pages_created)

    # Refresh index.md
    refresh_index()

    print(f"Processed {key} → {len(pages_created)} wiki pages")


def get_source_provenance(slug: str, raw_key: str) -> dict:
    """Read provenance fields from source registry; fall back to raw key only."""
    try:
        table = dynamodb.Table(REGISTRY_TABLE)
        resp = table.get_item(Key={"source_id": slug})
        item = resp.get("Item", {})
        original_upload = item.get("original_upload_key", "")
        assets_key = item.get("raw_assets_key", "")
        converted_key = item.get("converted_key", raw_key)
        return {
            "original_file": original_upload,
            "original_s3_uri": f"s3://{WIKI_BUCKET}/{original_upload}" if original_upload else "",
            "raw_markdown": converted_key or raw_key,
            "raw_assets": assets_key,
        }
    except Exception as e:
        print(f"WARN: Could not read provenance for {slug}: {e}")
        return {
            "original_file": "",
            "original_s3_uri": "",
            "raw_markdown": raw_key,
            "raw_assets": "",
        }


def generate_wiki_pages(source_text: str, slug: str, source_type: str, original_key: str, provenance: dict):
    """Call Bedrock Claude to generate structured wiki pages from the source."""

    schema = get_wiki_schema()

    original_file = provenance.get("original_file") or original_key
    original_uri = provenance.get("original_s3_uri") or f"s3://{WIKI_BUCKET}/{original_key}"

    prompt = f"""You are an LLMWiki page generator. Given a source document, you generate structured wiki pages in Markdown.

{schema}

SOURCE METADATA:
- File: {original_key}
- Original Upload: {original_file}
- Original S3 URI: {original_uri}
- Type: {source_type}
- Slug: {slug}

SOURCE CONTENT:
{source_text[:8000]}

INSTRUCTIONS:
Generate wiki pages for this source. Return a JSON array where each item has:
- "page_type": one of "sources", "entities", "concepts"
- "page_slug": kebab-case filename (no extension)
- "content": full Markdown content with YAML frontmatter

Required pages:
1. A source summary page (page_type: "sources", page_slug: "{slug}")
2. Up to 3 entity pages for key people, organizations, or systems mentioned
3. Up to 2 concept pages for key ideas or frameworks

Each page MUST include YAML frontmatter with: title, date, tags (list), source_count, status.
The source summary page frontmatter MUST also include:
  source_file: {original_key}
  original_upload: {original_file}
  original_s3_uri: {original_uri}
Entity and concept pages must include a ## Sources section listing this source.
All pages must use [[wikilinks]] to cross-reference related pages.

Return ONLY valid JSON, no explanation."""

    _converse_kwargs = {
        "modelId": MODEL_ID,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 8192},
    }
    response = bedrock.converse(**_converse_kwargs)
    raw_text = response["output"]["message"]["content"][0]["text"].strip()

    # Extract JSON from response
    json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if not json_match:
        print(f"WARN: Could not extract JSON from Claude response, creating minimal page")
        return create_minimal_page(slug, source_text, original_key, provenance)

    pages_data = json.loads(json_match.group())
    result = []
    for page in pages_data:
        result.append((page["page_type"], page["page_slug"], page["content"]))

    return result


def create_minimal_page(slug: str, source_text: str, original_key: str, provenance: dict):
    """Fallback: create a basic source summary page if Claude response parsing fails."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    original_file = provenance.get("original_file", "")
    original_uri = provenance.get("original_s3_uri", "")
    content = f"""---
title: {slug.replace('-', ' ').title()}
date: {now}
tags: [auto-generated]
source_count: 1
status: draft
source_file: {original_key}
original_upload: {original_file}
original_s3_uri: {original_uri}
---

# {slug.replace('-', ' ').title()}

*Auto-generated from {original_key}*

## Summary

{source_text[:1000]}

## Source

- `{original_key}`
"""
    return [("sources", slug, content)]


def get_wiki_schema() -> str:
    """Read AGENTS.md from S3 config, fall back to inline default."""
    try:
        response = s3.get_object(Bucket=WIKI_BUCKET, Key="config/AGENTS.md")
        return response["Body"].read().decode("utf-8")[:2000]
    except Exception:
        return """WIKI SCHEMA:
- sources/: One page per source document — summary, key takeaways, concepts mentioned
- entities/: Pages for people, organizations, systems, products
- concepts/: Pages for ideas, frameworks, methodologies
- All pages use [[wikilinks]] for cross-references
- YAML frontmatter: title, date, tags, source_count, status"""


def infer_source_type(key: str) -> str:
    if "/papers/" in key:
        return "paper"
    if "/articles/" in key:
        return "article"
    if "/notes/" in key:
        return "note"
    if "/youtube/" in key:
        return "transcript"
    if "/meetings/" in key:
        return "meeting"
    return "document"


def key_to_slug(key: str) -> str:
    basename = key.split("/")[-1]
    return re.sub(r"[^a-z0-9-]", "-", basename.replace(".md", "").lower()).strip("-")


def is_already_processed(slug: str) -> bool:
    table = dynamodb.Table(REGISTRY_TABLE)
    response = table.get_item(Key={"source_id": slug})
    item = response.get("Item", {})
    return item.get("status") == "wiki-page-created"


def update_wiki_index(page_type: str, page_slug: str, s3_key: str, now: str, source_type: str, provenance: dict):
    table = dynamodb.Table(INDEX_TABLE)
    item = {
        "page_type": page_type,
        "page_slug": page_slug,
        "s3_key": s3_key,
        "last_updated": now,
        "source_type": source_type,
        "status": "active",
    }
    # Embed provenance on source pages so Query Lambda and Streamlit can retrieve it
    if page_type == "sources" and provenance:
        item["source_provenance"] = json.dumps(provenance)
    table.put_item(Item=item)


def append_log(source_key: str, slug: str, pages_created: list, now: str):
    table = dynamodb.Table(LOG_TABLE)
    log_date = now[:10]
    timestamp_id = f"{now}#{slug}"
    table.put_item(Item={
        "log_date": log_date,
        "timestamp_id": timestamp_id,
        "operation": "ingest",
        "source_key": source_key,
        "source_slug": slug,
        "pages_created": pages_created,
        "page_count": len(pages_created),
    })


def mark_processed(slug: str, key: str, pages_created: list, now: str, provenance: dict):
    table = dynamodb.Table(REGISTRY_TABLE)
    item = {
        "source_id": slug,
        "source_key": key,
        "status": "wiki-page-created",
        "ingested_at": now,
        "pages_created": pages_created,
    }
    # Preserve provenance fields written by converter (or set raw markdown path)
    if provenance.get("original_file"):
        item["original_upload_key"] = provenance["original_file"]
    if provenance.get("raw_assets"):
        item["raw_assets_key"] = provenance["raw_assets"]
    table.put_item(Item=item)


def resolve_gaps_for_slug(slug: str, pages_created: list):
    """Mark any knowledge gaps as resolved when a real document covers that slug."""
    if not GAPS_TABLE:
        return
    try:
        table = dynamodb.Table(GAPS_TABLE)
        # Check if any gap with this slug exists
        resp = table.query(
            IndexName="slug_index",
            KeyConditionExpression="gap_slug = :s",
            FilterExpression="#st <> :r",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":s": slug, ":r": "resolved"},
        )
        now = datetime.now(timezone.utc).isoformat()
        for gap in resp.get("Items", []):
            table.update_item(
                Key={"gap_id": gap["gap_id"]},
                UpdateExpression="SET #st = :r, resolved_at = :t, resolved_by = :b",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":r": "resolved", ":t": now, ":b": slug},
            )
            print(f"  Gap resolved: {gap['gap_slug']}")
    except Exception as e:
        print(f"WARN: Could not resolve gaps for {slug}: {e}")


def refresh_index():
    """Rebuild wiki/index.md from DynamoDB index table."""
    table = dynamodb.Table(INDEX_TABLE)

    pages_by_type: dict = {}
    response = table.scan()
    for item in response.get("Items", []):
        pt = item.get("page_type", "other")
        pages_by_type.setdefault(pt, []).append(item)

    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        for item in response.get("Items", []):
            pt = item.get("page_type", "other")
            pages_by_type.setdefault(pt, []).append(item)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# LLMWiki Index\n\n*Last updated: {now}*\n"]

    for page_type in sorted(pages_by_type.keys()):
        lines.append(f"\n## {page_type.title()}\n")
        for item in sorted(pages_by_type[page_type], key=lambda x: x.get("page_slug", "")):
            slug = item["page_slug"]
            s3_key = item.get("s3_key", f"wiki/{page_type}/{slug}.md")
            updated = item.get("last_updated", "")[:10]
            status = item.get("status", "active")
            status_tag = " *(stub)*" if status == "stub" else ""
            lines.append(f"- [[{slug}]] — `{s3_key}` _{updated}_{status_tag}")

    index_content = "\n".join(lines)
    s3.put_object(
        Bucket=WIKI_BUCKET,
        Key="wiki/index.md",
        Body=index_content.encode("utf-8"),
        ContentType="text/markdown",
    )


def sync_knowledge_base():
    """Start a Bedrock KB ingestion job to index new wiki pages."""
    try:
        kb_id = ssm.get_parameter(Name=KB_ID_PARAM)["Parameter"]["Value"]
        ds_id = ssm.get_parameter(Name=KB_DS_PARAM)["Parameter"]["Value"]
    except Exception as e:
        print(f"WARN: Could not read KB params: {e}")
        return

    bedrock_agent = boto3.client("bedrock-agent", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    bedrock_agent.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
    )
    print(f"KB ingestion job started for KB {kb_id}")
