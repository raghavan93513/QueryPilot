"""Evaluation-only AutoGen runner: reuse one asyncio loop across SQL attempts.

The application itself still uses its normal generator and FastAPI routes.  This
scope is appropriate for sequential benchmark execution, not concurrent API
requests.  The model client is closed inside agents._autogen_team per call.
"""
import asyncio
from contextlib import contextmanager
from contextvars import copy_context
from threading import Lock
from typing import Callable, Iterator, Optional

from app import agents
from app.settings import backend_name


@contextmanager
def evaluation_generator(*, trace_enabled: bool = False) -> Iterator[Optional[Callable]]:
    """Yield None in mock mode, otherwise a sequential, reusable loop generator."""
    if backend_name() == "mock":
        yield None
        return

    team = agents._autogen_team
    if trace_enabled:
        from deepeval.tracing import observe, update_current_span

        underlying_team = team

        @observe(type="agent", name="autogen_sql_writer_and_reviewer")
        async def traced_team(question, schema, error, previous_sql):
            sql = await underlying_team(question, schema, error, previous_sql)
            update_current_span(
                input=question,
                output=sql,
                metadata={"retry": bool(previous_sql), "has_error_feedback": bool(error)},
            )
            return sql

        team = traced_team

    lock = Lock()
    with asyncio.Runner() as runner:
        def generate(question: str, schema: str, error: str = "", previous_sql: str = "") -> str:
            # LangGraph calls its synchronous node in a worker thread.  Passing
            # the caller's context preserves DeepEval's parent tracing context.
            with lock:
                return runner.run(
                    team(question, schema, error, previous_sql),
                    context=copy_context(),
                )

        yield generate
        # A final event-loop turn allows pending callbacks from awaited client
        # cleanup to run before Runner cancels remaining tasks at shutdown.
        runner.run(asyncio.sleep(0))
