"""
LLMWiki Harness Common Library — shared DynamoDB state management for
all harness Lambdas (UC1 Sales-to-Service, UC-PM Problem Management, etc.).

Each harness has its own DynamoDB table and key scheme but shares:
- Init / update / save-phase patterns
- TTL constant
- Phase result serialization
"""

import json
import time
from datetime import datetime, timezone

TTL_30_DAYS = 30 * 86400


def init_run(table, key: dict, extra: dict) -> None:
    """
    Write the initial run record.
    key   — the DynamoDB primary key dict, e.g. {"run_id": "...", "batch_id": "..."}
    extra — app-specific fields to merge into the item
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    item = {
        **key,
        "status":           "running",
        "current_phase":    1,
        "phases_completed": [],
        "phase_results":    json.dumps({}),
        "created_at":       now_iso,
        "updated_at":       now_iso,
        "expires_at":       int(time.time()) + TTL_30_DAYS,
    }
    item.update(extra)
    table.put_item(Item=item)


def update_run(table, key: dict, updates: dict) -> None:
    """
    Apply a partial update to a run record.
    key     — the DynamoDB primary key dict
    updates — fields to set (updated_at is added automatically)
    """
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_expr   = "SET " + ", ".join(f"#{k}=:{k}" for k in updates)
    expr_names = {f"#{k}": k for k in updates}
    expr_vals  = {f":{k}": v for k, v in updates.items()}
    table.update_item(
        Key=key,
        UpdateExpression=set_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_vals,
    )


def save_phase(table, key: dict, phase_num: int, result: dict) -> None:
    """
    Persist a single phase result into the phase_results JSON blob.
    Reads the existing record, merges the new phase, and writes back.
    """
    existing = table.get_item(Key=key).get("Item", {})
    saved    = json.loads(existing.get("phase_results", "{}"))
    saved[str(phase_num)] = result
    update_run(table, key, {
        "phase_results": json.dumps(saved, default=str),
        "current_phase": phase_num,
    })


def load_phases(table, key: dict) -> dict:
    """
    Load all saved phase results for a run.
    Returns a dict keyed by phase number string: {"1": {...}, "2": {...}, ...}
    """
    item = table.get_item(Key=key).get("Item", {})
    raw  = item.get("phase_results", "{}")
    return json.loads(raw) if isinstance(raw, str) else (raw or {})
