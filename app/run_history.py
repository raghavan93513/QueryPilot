"""Read-only, compact checkpoint history for UI and benchmark evidence.

This is LangGraph checkpoint history, not a per-token or per-LLM-call trace.
Never mutate checkpoints or inject feedback while reading them.
"""
from __future__ import annotations

from typing import Any


def _node(metadata: dict | None) -> str:
    metadata = metadata or {}
    writes = metadata.get("writes") or {}
    if isinstance(writes, dict) and writes:
        return ", ".join(str(key) for key in writes.keys())
    return str(metadata.get("source") or "checkpoint")


def snapshot_timeline(graph: Any, run_id: str, max_events: int = 100) -> list[dict]:
    """Return oldest-first checkpoint transitions for an existing thread.

    Keep the output intentionally small. No secrets, full schema payloads, or
    LLM prompts are included. SQL is included because the local user must
    inspect proposals and retries, so do not use this on a public API.
    """
    from app.workflow import config_for  # Delay LangGraph import until needed.

    snapshots = []
    for snap in graph.get_state_history(config_for(run_id), limit=max_events):
        values = snap.values or {}
        if not values:
            continue
        next_nodes = [str(n) for n in (snap.next or ())]
        tools = list(values.get("tool_calls") or [])
        snapshots.append({
            "at": str(snap.created_at) if snap.created_at is not None else None,
            "node": _node(snap.metadata),
            "status": "awaiting_approval" if "approval" in next_nodes else values.get("status", "unknown"),
            "next": next_nodes,
            "attempts": int(values.get("attempts") or 0),
            "sql": values.get("sql") or "",
            "error": values.get("error") or "",
            "tool_calls": tools,
            "rows_returned": len(values.get("rows") or []),
        })
    snapshots.reverse()
    return snapshots
