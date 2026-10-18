"""LangGraph finite-state machine with a real HITL interrupt and retry cycle."""
import sqlite3
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langgraph.checkpoint.sqlite import SqliteSaver

from app import agents, mock_agent
from app.settings import backend_name, attempts_limit, checkpoint_path
from app.sql_tools import SQLTools


class AgentState(TypedDict, total=False):
    question: str
    schema: str
    sql: str
    previous_sql: str
    error: str
    rows: list[dict]
    columns: list[str]
    attempts: int
    status: str
    answer: str
    tool_calls: list[str]
    feedback: str


def create_workflow(db=None, generator=None, checkpoint_file=None, max_attempts=None):
    """Dependency injection allows tests without a local language model."""
    db = db or SQLTools()
    if generator is None:
        generator = mock_agent.generate_mock_sql if backend_name() == "mock" else agents.generate_sql
    limit = max_attempts or attempts_limit()
    checkpoint_file = checkpoint_file or checkpoint_path()
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(checkpoint_file), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    def inspect_schema(state: AgentState):
        return {
            "schema": db.schema(),
            "tool_calls": state.get("tool_calls", []) + ["inspect_schema"],
            "status": "planning",
        }

    def draft(state: AgentState):
        attempt = state.get("attempts", 0) + 1
        sql = generator(
            state["question"], state["schema"],
            state.get("error", ""), state.get("previous_sql", ""),
        )
        return {"sql": sql, "attempts": attempt, "status": "awaiting_approval"}

    def approve(state: AgentState):
        # Keep this node free of side effects before interrupt(): the node re-runs on resume.
        decision = interrupt({
            "question": state["question"],
            "proposed_sql": state["sql"],
            "attempt": state["attempts"],
            "previous_error": state.get("error", ""),
            "instructions": "Approve execution, or reject with feedback.",
        })
        if not isinstance(decision, dict) or not isinstance(decision.get("approved"), bool):
            return {"status": "rejected", "feedback": "Invalid approval payload"}
        if not decision["approved"]:
            return {
                "status": "rejected", "error": decision.get("feedback", "Rejected by user"),
                "feedback": decision.get("feedback", "Rejected by user"),
                "previous_sql": state["sql"],
            }
        return {"status": "approved", "feedback": ""}

    def route_approval(state: AgentState):
        if state["status"] == "approved":
            return "execute"
        return "draft" if state["attempts"] < limit else "finish"

    def execute(state: AgentState):
        previous = state.get("tool_calls", []) + ["execute_sql"]
        try:
            result = db.execute(state["sql"])
            return {
                "rows": result["rows"], "columns": result["columns"],
                "sql": result["sql"], "error": "", "status": "executed",
                "tool_calls": previous,
            }
        except Exception as exc:
            return {
                "previous_sql": state["sql"],
                "error": f"{type(exc).__name__}: {exc}",
                "rows": [], "columns": [], "status": "query_failed",
                "tool_calls": previous,
            }

    def route_execute(state: AgentState):
        if state["status"] == "executed":
            return "finish"
        return "draft" if state["attempts"] < limit else "finish"

    def finish(state: AgentState):
        if state["status"] == "executed":
            rows = state.get("rows", [])
            if not rows:
                answer = "Query executed successfully, but returned zero rows."
            else:
                answer = (
                    f"Query completed. Returned {len(rows)} row(s). "
                    "See 'rows' for the exact database-backed results."
                )
            return {"status": "completed", "answer": answer}
        if state["status"] == "rejected":
            return {"status": "stopped", "answer": "SQL was rejected and retry budget was exhausted."}
        return {
            "status": "failed", "answer": f"Unable to produce a valid SQL result: {state.get('error', '')}",
        }

    graph = StateGraph(AgentState)
    graph.add_node("inspect_schema", inspect_schema)
    graph.add_node("draft", draft)
    graph.add_node("approval", approve)
    graph.add_node("execute", execute)
    graph.add_node("finish", finish)
    graph.add_edge(START, "inspect_schema")
    graph.add_edge("inspect_schema", "draft")
    graph.add_edge("draft", "approval")
    graph.add_conditional_edges("approval", route_approval, {"execute": "execute", "draft": "draft", "finish": "finish"})
    graph.add_conditional_edges("execute", route_execute, {"draft": "draft", "finish": "finish"})
    graph.add_edge("finish", END)
    compiled = graph.compile(checkpointer=checkpointer)
    # Keep SQLite connection alive for lifetime of the compiled workflow.
    return compiled


def config_for(thread_id: str):
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}


def current_view(graph, run_id: str) -> dict:
    snapshot = graph.get_state(config_for(run_id))
    state = snapshot.values or {}
    if not state:
        raise KeyError(run_id)
    paused = "approval" in snapshot.next
    return {
        "run_id": run_id,
        "status": "awaiting_approval" if paused else state.get("status", "unknown"),
        "question": state.get("question"),
        "proposed_sql": state.get("sql"),
        "attempts": state.get("attempts", 0),
        "previous_error": state.get("error", ""),
        "columns": state.get("columns", []),
        "rows": state.get("rows", []),
        "answer": state.get("answer", ""),
        "tool_calls": state.get("tool_calls", []),
    }
