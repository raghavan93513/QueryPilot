"""Two AutoGen agents use a local Qwen model to write and review SQL."""
import asyncio
import re
from app.settings import model_name, model_host

SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", flags=re.IGNORECASE | re.DOTALL)


def extract_sql(message: str) -> str:
    """Extract SQL from a model response without executing it."""
    match = SQL_FENCE.search(message)
    if match:
        return match.group(1).strip()
    return re.sub(r"^\s*SQL\s*:\s*", "", message.strip(), flags=re.IGNORECASE)


async def _autogen_team(question: str, schema: str, error: str, previous_sql: str) -> str:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_ext.models.ollama import OllamaChatCompletionClient

    client = OllamaChatCompletionClient(
        model=model_name(), host=model_host(),
        temperature=0.0,
    )
    try:
        writer = AssistantAgent(
            "sql_writer", model_client=client,
            system_message=(
                "You write only one DuckDB SELECT query. Use only provided tables and columns. "
                "For revenue, include only orders.status='completed' and use "
                "SUM(order_items.quantity * order_items.unit_price). "
                "Never write destructive SQL. Return only SQL inside a ```sql fenced block."
            ),
        )
        reviewer = AssistantAgent(
            "sql_reviewer", model_client=client,
            system_message=(
                "You review the previous assistant's SQL for schema accuracy, "
                "proper joins, completed-order filtering for revenue, and correct grouping. "
                "Fix mistakes. Output ONLY the corrected final SELECT SQL in a ```sql block."
            ),
        )
        group = RoundRobinGroupChat([writer, reviewer], max_turns=2)
        task = (
            f"User question: {question}\n\nSchema:\n{schema}\n\n"
            f"Previous failing SQL: {previous_sql or '(none)'}\n"
            f"Previous execution or user feedback: {error or '(none)'}\n"
            "Write an accurate query. The reviewer should correct it."
        )
        result = await group.run(task=task)
        responses = [m for m in result.messages if m.source == "sql_reviewer"]
        if not responses or not isinstance(responses[-1].content, str):
            raise RuntimeError("The SQL reviewer did not return text")
        return extract_sql(responses[-1].content)
    finally:
        await client.close()


def generate_sql(question: str, schema: str, error: str = "", previous_sql: str = "") -> str:
    """Synchronous LangGraph node boundary for async AutoGen team."""
    return asyncio.run(_autogen_team(question, schema, error, previous_sql))
