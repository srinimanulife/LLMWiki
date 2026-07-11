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

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

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


# OKF type mapping — LLMWiki page types to OKF-conformant type values
OKF_TYPE_MAP = {
    "sources":   "Source Summary",
    "entities":  "Entity",
    "concepts":  "Concept",
    "runbooks":  "Runbook",
    "customers": "Customer Context",
    "artifacts": "Artifact Template",
    "decisions": "Architecture Decision",
    "sops":      "SOP",
    "evidence":  "Evidence",
    "questions": "Knowledge Gap",
}


def validate_okf_conformant(content: str) -> bool:
    """OKF conformance: parseable YAML frontmatter + non-empty type field."""
    try:
        match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return False
        fm_text = match.group(1)
        # Parse manually if yaml unavailable
        if _yaml:
            fm = _yaml.safe_load(fm_text)
        else:
            fm = {}
            for line in fm_text.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip().strip('"')
        return bool(fm and fm.get("type"))
    except Exception:
        return False


def ensure_okf_type(content: str, page_type: str) -> str:
    """
    Inject OKF `type` field if missing from frontmatter.
    Also injects `resource` URI for source pages when it carries original_s3_uri.
    """
    import re as _re
    okf_type = OKF_TYPE_MAP.get(page_type, page_type.replace("_", " ").title())

    # Only patch if frontmatter exists and type is missing
    if "type:" not in content and content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            insert = f"\ntype: \"{okf_type}\""
            content = content[:end] + insert + content[end:]
    return content


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
    domain_prefixes_updated = set()

    for page_type, page_slug, content in wiki_pages:
        # OKF: ensure type field and inject resource URI for source pages
        content = ensure_okf_type(content, page_type)

        # OKF conformance check — retry once with corrective prompt if fails
        if not validate_okf_conformant(content):
            print(f"  WARN: OKF conformance failed for {page_type}/{page_slug}, retrying")
            content = fix_okf_conformance(content, page_type, page_slug)

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
        domain_prefixes_updated.add(page_type)

    # Append to log
    append_log(key, slug, pages_created, now)

    # Mark processed in source registry (preserves original provenance fields)
    mark_processed(slug, key, pages_created, now, provenance)

    # Resolve any gaps this document closes
    resolve_gaps_for_slug(slug, pages_created)

    # OKF: append to per-domain log.md and regenerate per-domain index.md
    for domain in domain_prefixes_updated:
        try:
            append_domain_log(domain, slug, pages_created, now)
            regenerate_domain_index(domain)
        except Exception as e:
            print(f"WARN: domain index update failed for {domain}: {e}")

    # Refresh master index.md
    refresh_index()

    print(f"Processed {key} → {len(pages_created)} wiki pages")


def fix_okf_conformance(content: str, page_type: str, page_slug: str) -> str:
    """Last-resort: build a minimal OKF-conformant frontmatter wrapper."""
    okf_type = OKF_TYPE_MAP.get(page_type, page_type.title())
    title    = page_slug.replace("-", " ").title()
    today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Strip any broken frontmatter
    import re as _re
    body = _re.sub(r'^---.*?---\s*', '', content, flags=_re.DOTALL).strip()
    return f"---\ntype: \"{okf_type}\"\ntitle: {title}\ndate: {today}\ntags: [auto-generated]\nstatus: draft\n---\n\n{body}"


def append_domain_log(domain: str, slug: str, pages_created: list, now: str):
    """Append OKF-style log entries to wiki/<domain>/log.md."""
    log_key = f"wiki/{domain}/log.md"
    try:
        existing = s3.get_object(Bucket=WIKI_BUCKET, Key=log_key)["Body"].read().decode("utf-8")
    except Exception:
        existing = f"# {domain.title()} — Change Log\n\n"

    date_str   = now[:10]
    new_entries = [f"\n## {date_str}\n"]
    domain_pages = [p for p in pages_created if p.startswith(f"{domain}/")]
    for page_path in domain_pages:
        ps = page_path.split("/", 1)[1] if "/" in page_path else page_path
        new_entries.append(f"**Creation** [{ps}.md]({ps}.md) — source: `{slug}`\n")

    if domain_pages:
        # Insert after existing header if date section already exists for today
        if date_str in existing:
            content = existing + "\n".join(new_entries[1:])  # skip date header (already there)
        else:
            # Find first ## section and insert before it, or append
            parts = existing.split("\n## ", 1)
            if len(parts) == 2:
                content = parts[0] + "\n" + "\n".join(new_entries) + "\n## " + parts[1]
            else:
                content = existing + "\n".join(new_entries)
        s3.put_object(Bucket=WIKI_BUCKET, Key=log_key,
                      Body=content.encode("utf-8"), ContentType="text/markdown")


def regenerate_domain_index(domain: str):
    """Regenerate OKF-conformant index.md for a specific wiki domain."""
    prefix = f"wiki/{domain}/"
    paginator = s3.get_paginator("list_objects_v2")
    pages = []
    for page in paginator.paginate(Bucket=WIKI_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if k.endswith(".md") and not k.endswith("/index.md") and not k.endswith("/log.md"):
                slug  = k.replace(prefix, "").replace(".md", "")
                pages.append({"slug": slug, "key": k, "modified": obj.get("LastModified")})

    pages.sort(key=lambda x: x.get("modified") or "", reverse=True)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    okf_type = OKF_TYPE_MAP.get(domain, domain.title())

    lines = [
        "---",
        f'type: "Index"',
        f"title: {domain.title()} — Knowledge Index",
        f"timestamp: {now_str}",
        "---",
        "",
        f"# {domain.title()} — Knowledge Index",
        "",
        f"*{len(pages)} page{'s' if len(pages) != 1 else ''} · Last updated: {now_str}*",
        "",
    ]
    for p in pages:
        slug  = p["slug"]
        title = slug.replace("-", " ").title()
        mod   = p["modified"].strftime("%Y-%m-%d") if p.get("modified") else ""
        lines.append(f"- [{title}]({slug}.md)  _{mod}_")

    s3.put_object(
        Bucket=WIKI_BUCKET,
        Key=f"{prefix}index.md",
        Body="\n".join(lines).encode("utf-8"),
        ContentType="text/markdown",
    )


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

    prompt = f"""You are an LLMWiki page generator. Generate structured wiki pages in the Open Knowledge Format (OKF).

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

OKF CONFORMANCE — every page MUST include in YAML frontmatter:
  type: "Source Summary"  (for sources), "Entity" (for entities), "Concept" (for concepts)
  title: <descriptive title>
  description: <one-sentence summary>
  date: <YYYY-MM-DD>
  tags: [list]
  status: active
  resource: {original_uri}   (include on ALL pages — the source this page was derived from)

The source summary page frontmatter MUST ALSO include:
  source_file: {original_key}
  original_upload: {original_file}
  original_s3_uri: {original_uri}

Entity and concept pages must include a ## Sources section referencing this source.
All pages must use [[wikilinks]] to cross-reference related pages.
In the body, add a ## Citations section listing the source document.

Return ONLY valid JSON array, no explanation."""

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
