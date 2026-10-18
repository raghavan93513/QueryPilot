"""Explicit benchmark requirements for schema-first SQL agent evaluation.

This module does NOT modify model prompts or bypass production controls. It
records an already implemented architectural constraint for evaluation.
"""

SCHEMA_FIRST_POLICY = (
    "Project execution constraints (required in addition to the business question):\n"
    "- Verify the live allowlisted database schema with inspect_schema once BEFORE "
    "generating the first SQL proposal; do not assume table or column names from memory.\n"
    "- Use the SQL writer/reviewer agent workflow to propose SQL.\n"
    "- Require human approval for each new SQL proposal, including repairs.\n"
    "- Enforce read-only SQL validation and execution.\n"
    "- Avoid duplicate schema inspections when the schema is unchanged, unnecessary "
    "agent rounds, invalid joins/columns, failed execution, and avoidable retries.\n"
    "Evaluate efficiency subject to these constraints, rather than treating a "
    "single required upfront schema inspection as optional."
)


def judge_trace_input(question: str, policy: str = "raw") -> str:
    """Describe the actual benchmark task for trace-only evaluation.

    The user question passed to LangGraph stays unchanged. 'schema-required'
    expands the judge's TASK DEFINITION to include the real system policy.
    Raw and policy-conditioned Step Efficiency scores are not comparable.
    """
    if policy == "raw":
        return question
    if policy != "schema-required":
        raise ValueError(f"Unknown judge policy: {policy}")
    return f"Business question: {question}\n\n{SCHEMA_FIRST_POLICY}"


def schema_policy_observed(tool_calls) -> bool:
    """Check recorded required-tool order; graph design controls draft order.

    Checkpoints expose tool names, not draft-node events. Therefore this check
    alone proves 'one inspect before execution', not 'before drafting'. The
    LangGraph edge inspect_schema -> draft enforces the latter.
    """
    calls = list(tool_calls or [])
    return (len(calls) >= 2 and
            calls[0] == "inspect_schema" and
            calls.count("inspect_schema") == 1 and
            "execute_sql" in calls and
            calls.index("execute_sql") > 0)
