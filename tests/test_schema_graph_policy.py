"""Integration: actual LangGraph must inspect the schema before any draft.

Runs with a synthetic DuckDB and stub SQL writer; no Qwen or DeepEval judge.
"""
from langgraph.types import Command
from app.seed import seed
from app.sql_tools import SQLTools
from app.workflow import create_workflow, config_for, current_view
from evaluation.workflow_policy import schema_policy_observed


def test_schema_is_checked_before_draft_and_only_once_on_retries(tmp_path):
    source = SQLTools(seed(tmp_path / "shop.duckdb"))
    calls = []

    class DB:
        def schema(self):
            calls.append("schema")
            return source.schema()

        def execute(self, sql):
            calls.append("execute")
            return source.execute(sql)

    def writer(question, schema, error, previous_sql):
        calls.append("draft")
        assert "customers.customer_id" in schema
        if not previous_sql:
            return "SELECT nonexistent_column FROM customers"
        return "SELECT COUNT(*) AS customer_count FROM customers"

    graph = create_workflow(
        db=DB(), generator=writer,
        checkpoint_file=tmp_path / "policy-checkpoints.sqlite", max_attempts=3,
    )
    thread_id = "check-schema-policy"
    graph.invoke(
        {"question": "Count customers", "attempts": 0, "tool_calls": []},
        config_for(thread_id),
    )
    assert calls == ["schema", "draft"]
    assert current_view(graph, thread_id)["status"] == "awaiting_approval"

    graph.invoke(Command(resume={"approved": True, "feedback": ""}),
                 config_for(thread_id))
    assert calls == ["schema", "draft", "execute", "draft"]
    assert current_view(graph, thread_id)["status"] == "awaiting_approval"

    graph.invoke(Command(resume={"approved": True, "feedback": ""}),
                 config_for(thread_id))
    result = current_view(graph, thread_id)
    assert result["status"] == "completed"
    assert result["rows"][0]["customer_count"] == 8
    assert calls == ["schema", "draft", "execute", "draft", "execute"]
    assert schema_policy_observed(result["tool_calls"])
