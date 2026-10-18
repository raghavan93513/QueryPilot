"""Full LangGraph + checkpoint + mock-agent integration tests, no Ollama required."""
from app.seed import seed
from app.sql_tools import SQLTools
from app.workflow import create_workflow, config_for, current_view
from app.mock_agent import generate_mock_sql
from langgraph.types import Command


def workflow(tmp_path, limit=3):
    db = SQLTools(seed(tmp_path / "shop.duckdb"))
    return create_workflow(
        db=db, generator=generate_mock_sql,
        checkpoint_file=tmp_path / "checkpoints.sqlite", max_attempts=limit,
    )


def start(graph, thread_id, question):
    graph.invoke({"question": question, "attempts": 0, "tool_calls": []}, config_for(thread_id))
    return current_view(graph, thread_id)


def resume(graph, thread_id, approved=True, feedback=""):
    graph.invoke(Command(resume={"approved": approved, "feedback": feedback}), config_for(thread_id))
    return current_view(graph, thread_id)


def test_human_approval_required(tmp_path):
    graph = workflow(tmp_path)
    view = start(graph, "approval", "How many customers?")
    assert view["status"] == "awaiting_approval"
    assert "execute_sql" not in view["tool_calls"]
    complete = resume(graph, "approval")
    assert complete["status"] == "completed"
    assert complete["rows"][0]["customer_count"] == 8
    assert "execute_sql" in complete["tool_calls"]


def test_rejection_returns_for_new_approval(tmp_path):
    graph = workflow(tmp_path)
    start(graph, "reject", "How many customers?")
    next_view = resume(graph, "reject", False, "I want you to reconsider")
    assert next_view["status"] == "awaiting_approval"
    assert next_view["attempts"] == 2
    assert "execute_sql" not in next_view["tool_calls"]


def test_query_error_repairs_by_cycling(tmp_path):
    graph = workflow(tmp_path)
    start(graph, "repair", "Please repair this customer count query")
    paused = resume(graph, "repair", True)
    assert paused["status"] == "awaiting_approval"
    assert paused["attempts"] == 2
    assert "nonexistent_column" in paused["previous_error"]
    done = resume(graph, "repair", True)
    assert done["status"] == "completed"
    assert done["rows"][0]["customer_count"] == 8


def test_destructive_sql_never_runs(tmp_path):
    graph = workflow(tmp_path, limit=2)
    start(graph, "unsafe", "inject unsafe query")
    second = resume(graph, "unsafe", True)
    assert second["status"] == "awaiting_approval"
    finished = resume(graph, "unsafe", True)
    assert finished["status"] == "failed"
    assert SQLTools(tmp_path / "shop.duckdb").execute("SELECT COUNT(*) AS n FROM customers")["rows"][0]["n"] == 8
