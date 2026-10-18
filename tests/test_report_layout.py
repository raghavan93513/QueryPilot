"""Reports have one canonical location; temporary data is not a report source."""
import json
from app import dashboard


def test_catalog_only_scans_reports(monkeypatch, tmp_path):
    data = tmp_path / "data"
    published = tmp_path / "reports"
    generated = published / "generated"
    data.mkdir(); generated.mkdir(parents=True)
    example = [{"question": "Q", "passed": True, "status": "completed"}]
    (data / "old_duplicate.json").write_text(json.dumps(example))
    (published / "benchmark_5.json").write_text(json.dumps(example))
    (generated / "benchmark_extended_123.json").write_text(json.dumps(example))
    monkeypatch.setattr(dashboard, "DATA_DIR", data)
    monkeypatch.setattr(dashboard, "REPORTS_DIR", published)
    catalog = dashboard.report_catalog()
    assert len(catalog) == 2
    assert {x["origin"] for x in catalog} == {"published", "generated"}


def test_judge_summary_fallback(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    published = tmp_path / "reports"
    published.mkdir()
    (published / "judge_summary.json").write_text(json.dumps({"task_completion": 0.99}))
    monkeypatch.setattr(dashboard, "REPORTS_DIR", published)
    app = FastAPI(); dashboard.mount_dashboard(app, workflow=None)
    result = TestClient(app).get("/api/ui/judge-summary")
    assert result.status_code == 200
    assert result.json()["task_completion"] == 0.99


def test_evaluation_job_targets_generated_reports(monkeypatch, tmp_path):
    from app.dashboard import EvalJobManager, EvaluationRequest
    class DummyProcess:
        def poll(self):
            return None
    commands = []
    def popen(command, **kwargs):
        commands.append(command)
        return DummyProcess()
    monkeypatch.setattr(dashboard, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(dashboard, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(dashboard.subprocess, "Popen", popen)
    manager = EvalJobManager()
    state = manager.start(EvaluationRequest(suite="extended", mode="standard"))
    assert state["state"] == "running"
    command = commands[0]
    assert command[command.index("--output") + 1].startswith(str(tmp_path / "reports" / "generated"))
    assert "--trace-output" not in command
    manager._log_handle.close()


def test_advanced_evaluation_trace_uses_generated_reports(monkeypatch, tmp_path):
    from app.dashboard import EvalJobManager, EvaluationRequest
    class DummyProcess:
        def poll(self):
            return None
    calls = []
    def popen(command, **kwargs):
        calls.append(command)
        return DummyProcess()
    monkeypatch.setattr(dashboard, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(dashboard, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(dashboard.subprocess, "Popen", popen)
    manager = EvalJobManager()
    manager.start(EvaluationRequest(suite="baseline", mode="advanced", judge_limit=5))
    command = calls[0]
    assert "--judge-only" in command
    assert command[command.index("--trace-output") + 1].startswith(str(tmp_path / "reports" / "generated"))
    manager._log_handle.close()
