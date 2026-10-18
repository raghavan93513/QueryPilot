"""No Ollama or paid judge required: verify the persistent asyncio loop scope."""
import asyncio

from evaluation import agent_runtime


def test_evaluation_generator_reuses_and_closes_loop(monkeypatch):
    monkeypatch.setattr(agent_runtime, "backend_name", lambda: "real")
    observed = []

    async def fake_team(*args):
        loop = asyncio.get_running_loop()
        observed.append(loop)
        await asyncio.sleep(0)
        return "SELECT 1"

    monkeypatch.setattr(agent_runtime.agents, "_autogen_team", fake_team)

    with agent_runtime.evaluation_generator() as generator:
        assert generator("question 1", "schema") == "SELECT 1"
        assert generator("question 2", "schema") == "SELECT 1"
        assert observed[0] is observed[1]
        assert not observed[0].is_closed()

    assert observed[0].is_closed()


def test_mock_mode_does_not_create_runner(monkeypatch):
    monkeypatch.setattr(agent_runtime, "backend_name", lambda: "mock")
    with agent_runtime.evaluation_generator() as generator:
        assert generator is None


def test_evaluation_generator_propagates_context(monkeypatch):
    from contextvars import ContextVar

    marker = ContextVar("trace_marker", default="missing")
    monkeypatch.setattr(agent_runtime, "backend_name", lambda: "real")

    async def fake_team(*args):
        return marker.get()

    monkeypatch.setattr(agent_runtime.agents, "_autogen_team", fake_team)
    with agent_runtime.evaluation_generator() as generator:
        token = marker.set("parent-trace")
        try:
            assert generator("question", "schema") == "parent-trace"
        finally:
            marker.reset(token)
