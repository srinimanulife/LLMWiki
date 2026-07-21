"""
Step 2 — Read traces from Phoenix and categorise failures BEFORE writing evals.

Pulls spans from Phoenix, prints a summary table, categorises each trace
into one of four failure buckets, and writes a categorisation CSV that
step3 uses to prioritise which evals to run.

Usage:
    python eval/step2_read_traces.py
    python eval/step2_read_traces.py --project llmwiki-query --limit 50
    python eval/step2_read_traces.py --save-csv /tmp/trace_categories.csv
"""

import argparse
import csv
import os
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from phoenix_config import PHOENIX_ENDPOINT, PROJECT_LAMBDA

# ── Failure categories ─────────────────────────────────────────────────────
CATEGORY_EMPTY_ANSWER      = "empty_answer"
CATEGORY_NO_CONTEXT        = "no_context"
CATEGORY_OVERCONFIDENT     = "overconfident"
CATEGORY_LOW_CONFIDENCE    = "low_confidence"
CATEGORY_OK                = "ok"


def _phoenix_get(path: str) -> dict:
    url = f"{PHOENIX_ENDPOINT}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Phoenix GET {path} → {e.code}: {body}") from e


def get_spans(project_name: str, limit: int) -> list[dict]:
    """
    Fetch spans from Phoenix via its REST API.
    Uses GET /v1/projects/{project_identifier}/spans (Phoenix v1 REST API).
    Returns a list of flat dicts with the key fields we need.
    """
    try:
        # Phoenix REST v1: project name as path segment
        path = f"/v1/projects/{project_name}/spans?limit={limit}"
        data = _phoenix_get(path)
        raw_spans = data.get("data", [])
    except Exception as e:
        print(f"WARN: Phoenix REST API failed ({e}). Trying GraphQL fallback...")
        raw_spans = _get_spans_graphql(project_name, limit)

    spans = []
    for s in raw_spans:
        attrs = s.get("attributes", {})
        # Normalise — REST returns dict, GraphQL may return list
        if isinstance(attrs, list):
            attrs = {a["key"]: a.get("value", {}).get("stringValue") or
                              a.get("value", {}).get("intValue") or "" for a in attrs}

        # span_id: REST returns context.span_id; fall back to top-level id
        ctx = s.get("context", {})
        span_id = ctx.get("span_id") or s.get("spanId") or s.get("id", "")

        # latency: compute from ISO timestamps if latencyNs not present
        latency_ns = int(s.get("latencyNs", s.get("latency_ns", 0)) or 0)
        if not latency_ns:
            try:
                import datetime
                fmt = "%Y-%m-%dT%H:%M:%S.%f+00:00"
                t0 = datetime.datetime.fromisoformat(s["start_time"].replace("Z", "+00:00"))
                t1 = datetime.datetime.fromisoformat(s["end_time"].replace("Z", "+00:00"))
                latency_ns = int((t1 - t0).total_seconds() * 1e9)
            except Exception:
                latency_ns = 0

        spans.append({
            "span_id":    span_id,
            "name":       s.get("name", ""),
            "input":      attrs.get("input.value", ""),
            "output":     attrs.get("output.value", ""),
            "context":    attrs.get("llmwiki.retrieved_context", ""),
            "confidence": attrs.get("llmwiki.confidence", ""),
            "domain":     attrs.get("llmwiki.domain", ""),
            "citations":  str(attrs.get("llmwiki.citation_count", "0")),
            "latency_ns": latency_ns,
        })
    return spans


def _get_spans_graphql(project_name: str, limit: int) -> list[dict]:
    """Fallback: query Phoenix via its GraphQL endpoint."""
    query = """
    query GetSpans($projectName: String!, $first: Int!) {
      spans(projectName: $projectName, first: $first) {
        edges {
          node {
            spanId
            name
            latencyMs
            attributes
          }
        }
      }
    }
    """
    payload = json.dumps({
        "query": query,
        "variables": {"projectName": project_name, "first": limit}
    }).encode()
    req = urllib.request.Request(
        f"{PHOENIX_ENDPOINT}/graphql",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        edges = result.get("data", {}).get("spans", {}).get("edges", [])
        spans = []
        for edge in edges:
            node = edge["node"]
            raw_attrs = node.get("attributes", {})
            if isinstance(raw_attrs, str):
                try:
                    raw_attrs = json.loads(raw_attrs)
                except Exception:
                    raw_attrs = {}
            node["attributes"] = raw_attrs
            node["spanId"]     = node.get("spanId", "")
            node["latencyNs"]  = int(node.get("latencyMs", 0) or 0) * 1_000_000
            spans.append(node)
        return spans
    except Exception as e:
        print(f"WARN: GraphQL fallback also failed: {e}")
        return []


def categorise(span: dict) -> str:
    answer   = str(span.get("output",     "")).strip()
    context  = str(span.get("context",    "")).strip()
    conf     = str(span.get("confidence", "")).lower()
    try:
        citations = int(span.get("citations", 0))
    except (ValueError, TypeError):
        citations = 0

    if len(answer) < 20:
        return CATEGORY_EMPTY_ANSWER
    if len(context) < 10:
        return CATEGORY_NO_CONTEXT
    if conf == "high" and citations == 0:
        return CATEGORY_OVERCONFIDENT
    if conf == "low":
        return CATEGORY_LOW_CONFIDENCE
    return CATEGORY_OK


def analyse(spans: list[dict]) -> dict:
    counts = {
        CATEGORY_OK:             0,
        CATEGORY_EMPTY_ANSWER:   0,
        CATEGORY_NO_CONTEXT:     0,
        CATEGORY_OVERCONFIDENT:  0,
        CATEGORY_LOW_CONFIDENCE: 0,
    }
    categorised = []
    for s in spans:
        cat = categorise(s)
        counts[cat] += 1
        s["category"] = cat
        categorised.append(s)
    return {"counts": counts, "spans": categorised}


def print_report(result: dict, project_name: str) -> None:
    counts  = result["counts"]
    spans   = result["spans"]
    total   = len(spans)

    print(f"\n=== Step 2: Trace Analysis — project '{project_name}' ({total} spans) ===\n")

    if total == 0:
        print("  No spans found. Run step1_seed_traces.py first.")
        return

    # Category summary
    print("  Failure category breakdown:")
    print(f"    {'Category':<25} {'Count':>5}  {'%':>5}")
    print(f"    {'-'*40}")
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / total if total else 0
        marker = "  ✓" if cat == CATEGORY_OK else "  !"
        print(f"  {marker} {cat:<25} {count:>5}  {pct:>5.1f}%")

    # Confidence distribution
    conf_counts: dict[str, int] = {}
    for s in spans:
        c = s.get("confidence", "unknown")
        conf_counts[c] = conf_counts.get(c, 0) + 1
    print(f"\n  Confidence distribution:")
    for c, n in sorted(conf_counts.items(), key=lambda x: -x[1]):
        print(f"    {c:<10} {n}")

    # Domain distribution
    domain_counts: dict[str, int] = {}
    for s in spans:
        d = s.get("domain", "unknown")
        domain_counts[d] = domain_counts.get(d, 0) + 1
    print(f"\n  Domain distribution:")
    for d, n in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"    {d:<25} {n}")

    # Flagged spans worth reviewing
    problems = [s for s in spans if s["category"] != CATEGORY_OK]
    if problems:
        print(f"\n  Flagged spans ({len(problems)} — review before writing evals):")
        for s in problems[:10]:
            q = s.get("input", "")[:65]
            print(f"    [{s['category']:<20}] {q}")

    # Eval recommendations
    print("\n  Eval recommendations based on this trace set:")
    if counts.get(CATEGORY_NO_CONTEXT, 0) > 0 or counts.get(CATEGORY_EMPTY_ANSWER, 0) > 0:
        print("    → Run code evals first (step3) — structural failures present")
    if total - counts.get(CATEGORY_EMPTY_ANSWER, 0) > 3:
        print("    → Run faithfulness eval (step3) — sufficient traces with context")
    if counts.get(CATEGORY_OVERCONFIDENT, 0) > 0:
        print("    → Add confidence calibration eval — overconfident traces found")
    if counts.get(CATEGORY_LOW_CONFIDENCE, 0) > 0:
        print("    → Check KB coverage — low-confidence traces suggest retrieval gaps")


def save_csv(spans: list[dict], path: str) -> None:
    fieldnames = ["span_id", "name", "domain", "confidence", "citations",
                  "category", "input", "output", "context", "latency_ns"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(spans)
    print(f"\n  Categories saved → {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read and analyse Phoenix traces")
    parser.add_argument("--project",  default=PROJECT_LAMBDA)
    parser.add_argument("--limit",    type=int, default=100)
    parser.add_argument("--save-csv", default="", help="Path to write categorisation CSV")
    args = parser.parse_args()

    spans  = get_spans(args.project, args.limit)
    result = analyse(spans)
    print_report(result, args.project)

    if args.save_csv:
        save_csv(result["spans"], args.save_csv)
    else:
        default_csv = os.path.join(os.path.dirname(__file__), "trace_categories.csv")
        save_csv(result["spans"], default_csv)
