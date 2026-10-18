"""Policies are evaluated independently of LLM-judge opinions."""
import pytest
from evaluation.workflow_policy import (judge_trace_input, schema_policy_observed,
                                        SCHEMA_FIRST_POLICY)


def test_raw_mode_preserves_trace_task():
    question = "How many customers are there?"
    assert judge_trace_input(question, "raw") == question


def test_schema_required_task_adds_real_architecture_requirements():
    question = "How many customers are there?"
    task = judge_trace_input(question, "schema-required")
    assert question in task
    assert "inspect_schema once BEFORE" in task
    assert "human approval" in task
    assert "unnecessary" in task
    assert SCHEMA_FIRST_POLICY in task


def test_policy_mode_rejects_unsupported_value():
    with pytest.raises(ValueError):
        judge_trace_input("Count", "pretend-all-good")


def test_schema_inspection_once_before_execution_required():
    assert schema_policy_observed(["inspect_schema", "execute_sql"])
    assert schema_policy_observed(["inspect_schema", "execute_sql", "execute_sql"])
    assert not schema_policy_observed(["execute_sql"])
    assert not schema_policy_observed(["execute_sql", "inspect_schema"])
    assert not schema_policy_observed(["inspect_schema", "inspect_schema", "execute_sql"])
    assert not schema_policy_observed(["inspect_schema"])


def test_policy_does_not_claim_absence_of_retries():
    # The architectural requirement is not proof the model avoids SQL failures.
    assert schema_policy_observed(["inspect_schema", "execute_sql", "execute_sql"])
