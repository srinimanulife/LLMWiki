"""
Converter Lambda — Phase 1
Triggered by S3 ObjectCreated on uploads/
Converts PDF/DOCX/PPTX/XLSX to Markdown using Textract (PDF)
or Bedrock Claude (Office docs), then drops .md in raw/.
"""

import json
import os
import re
import boto3
import urllib.parse
from datetime import datetime, timezone

s3 = boto3.client("s3")
textract = boto3.client("textract", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb")

WIKI_BUCKET = os.environ["WIKI_BUCKET"]
REGISTRY_TABLE = os.environ["REGISTRY_TABLE"]
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

SUPPORTED_EXTENSIONS = {
    ".pdf": "paper",
    ".docx": "notes",
    ".doc": "notes",
    ".pptx": "articles",
    ".ppt": "articles",
    ".xlsx": "notes",
    ".xls": "notes",
    ".txt": "notes",
    ".csv": "notes",
}


def lambda_handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        size = record["s3"]["object"].get("size", 0)

        print(f"Converter received: s3://{bucket}/{key} ({size} bytes)")

        ext = os.path.splitext(key)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            print(f"Skipping unsupported extension: {ext}")
            continue

        try:
            convert_and_place(bucket, key, ext, size)
        except Exception as e:
            print(f"ERROR converting {key}: {e}")
            mark_failed(key, str(e))
            raise

    return {"statusCode": 200, "body": "Conversion complete"}


def convert_and_place(bucket: str, key: str, ext: str, size: int):
    source_type = SUPPORTED_EXTENSIONS[ext]
    basename = os.path.basename(key)
    slug = re.sub(r"[^a-z0-9-]", "-", os.path.splitext(basename)[0].lower()).strip("-")
    target_key = f"raw/{source_type}/{slug}.md"

    # Check if already converted
    try:
        s3.head_object(Bucket=WIKI_BUCKET, Key=target_key)
        print(f"Already converted: {target_key}")
        return
    except s3.exceptions.ClientError:
        pass

    if ext == ".pdf":
        markdown = convert_pdf_textract(bucket, key)
    elif ext in (".xlsx", ".xls", ".csv"):
        markdown = convert_tabular(bucket, key, ext, slug)
    else:
        markdown = convert_text_bedrock(bucket, key, ext, slug)

    if not markdown or len(markdown.strip()) < 20:
        raise ValueError(f"Conversion produced empty output for {key}")

    # Wrap with frontmatter
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    full_content = f"""---
title: {slug.replace('-', ' ').title()}
date: {now}
source_file: {key}
source_type: {source_type}
converted_by: llmwiki-converter
tags: [auto-converted, {source_type}]
status: raw
---

{markdown}
"""

    # Write to raw/
    s3.put_object(
        Bucket=WIKI_BUCKET,
        Key=target_key,
        Body=full_content.encode("utf-8"),
        ContentType="text/markdown",
    )
    print(f"Converted {key} → {target_key}")

    # Save original to assets
    try:
        s3.copy_object(
            Bucket=WIKI_BUCKET,
            CopySource={"Bucket": bucket, "Key": key},
            Key=f"raw/assets/{basename}",
        )
    except Exception as e:
        print(f"WARN: Could not copy to assets: {e}")

    assets_key = f"raw/assets/{basename}"
    mark_converted(slug, key, target_key, assets_key)


def convert_pdf_textract(bucket: str, key: str) -> str:
    """Use Amazon Textract to extract text from a PDF stored in S3."""
    print(f"Textract: extracting {key}")

    response = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )
    job_id = response["JobId"]

    # Poll for completion
    import time
    for _ in range(60):
        result = textract.get_document_text_detection(JobId=job_id)
        status = result["JobStatus"]
        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            raise RuntimeError(f"Textract failed for {key}: {result.get('StatusMessage')}")
        time.sleep(5)
    else:
        raise TimeoutError(f"Textract timed out for {key}")

    # Collect all pages
    lines = []
    pages_data = [result]
    while "NextToken" in result:
        result = textract.get_document_text_detection(JobId=job_id, NextToken=result["NextToken"])
        pages_data.append(result)

    current_page = 0
    for page_data in pages_data:
        for block in page_data.get("Blocks", []):
            if block["BlockType"] == "PAGE":
                current_page = block.get("Page", current_page + 1)
                lines.append(f"\n## Page {current_page}\n")
            elif block["BlockType"] == "LINE":
                lines.append(block.get("Text", ""))

    return "\n".join(lines)


def convert_text_bedrock(bucket: str, key: str, ext: str, slug: str) -> str:
    """Use Bedrock Claude to convert Office docs to clean Markdown."""
    # Read raw bytes and try to extract text
    response = s3.get_object(Bucket=WIKI_BUCKET, Key=key)
    raw_bytes = response["Body"].read()

    # For PPTX/DOCX we can attempt basic text extraction via python-pptx/docx
    # In Lambda without layers, we use Bedrock to describe the file and generate markdown
    # For a real deployment, add python-docx and python-pptx Lambda layers

    prompt = f"""The following is raw text extracted from a {ext} file named "{slug}".
Convert it to clean, well-structured Markdown with proper headings and formatting.
Preserve all important information. Use ## for major sections, ### for subsections.
Remove formatting artifacts and redundant whitespace.

RAW TEXT:
{raw_bytes.decode('utf-8', errors='replace')[:6000]}

Return ONLY the converted Markdown, no explanation."""

    _converse_kwargs = {
        "modelId": MODEL_ID,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 4096},
    }
    response = bedrock.converse(**_converse_kwargs)
    return response["output"]["message"]["content"][0]["text"].strip()


def convert_tabular(bucket: str, key: str, ext: str, slug: str) -> str:
    """Convert CSV/Excel to a Markdown table."""
    response = s3.get_object(Bucket=WIKI_BUCKET, Key=key)
    raw = response["Body"].read().decode("utf-8", errors="replace")

    lines = raw.split("\n")[:100]  # first 100 rows

    if not lines:
        return ""

    # Simple CSV → Markdown table
    rows = [line.split(",") for line in lines if line.strip()]
    if not rows:
        return ""

    md_lines = []
    header = rows[0]
    md_lines.append("| " + " | ".join(h.strip().strip('"') for h in header) + " |")
    md_lines.append("|" + "|".join([" --- "] * len(header)) + "|")
    for row in rows[1:]:
        md_lines.append("| " + " | ".join(c.strip().strip('"') for c in row) + " |")

    return "\n".join(md_lines)


def mark_converted(slug: str, source_key: str, target_key: str, assets_key: str):
    table = dynamodb.Table(REGISTRY_TABLE)
    now = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        "source_id": slug,
        "source_key": source_key,
        "original_upload_key": source_key,
        "raw_assets_key": assets_key,
        "converted_key": target_key,
        "status": "converted",
        "ingested_at": now,
    })


def mark_failed(key: str, error: str):
    slug = re.sub(r"[^a-z0-9-]", "-", os.path.basename(key).lower()).strip("-")
    table = dynamodb.Table(REGISTRY_TABLE)
    now = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        "source_id": slug,
        "source_key": key,
        "original_upload_key": key,
        "status": "conversion-failed",
        "ingested_at": now,
        "error": error[:500],
    })
