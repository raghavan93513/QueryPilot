"""Local frontend/report tests. No Qwen model or real SQL data required."""
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import dashboard


def test_summary_calculation():
    report = [
        {"question":"A", "passed":True, "status":"completed", "attempts":1,
         "tool_correctness":1.0, "schema_verified_once":True, "trace":[{"node":"draft"}]},
        {"question":"B", "passed":False, "status":"completed", "attempts":2,
         "tool_correctness":1.0, "schema_verified_once":True},
    ]
    s = dashboard.summarize(report)
    assert (s["accuracy"], s["average_attempts"], s["first_try"]) == (50.0, 1.5, 1)
    assert (s["completed"], s["schema_verified"], s["traced_cases"]) == (2, 2, 1)


def test_report_catalog_and_detail(monkeypatch, tmp_path):
    data = tmp_path / "data"
    reports = tmp_path / "reports"
    data.mkdir();reports.mkdir()
    report = [{"question":"How many?", "passed":True, "actual_rows":[{"n":8}],
               "expected_rows":[[8]],"attempts":1,"status":"completed"}]
    (reports / "benchmark_5.json").write_text(json.dumps(report))
    (data / "private.json").write_text(json.dumps({"secret": "should-not-be-a-report"}))
    monkeypatch.setattr(dashboard, "DATA_DIR", data)
    monkeypatch.setattr(dashboard, "REPORTS_DIR", reports)
    app = FastAPI()
    dashboard.mount_dashboard(app, workflow=None)
    client = TestClient(app)
    index = client.get("/")
    assert index.status_code == 200 and "QueryPilot" in index.text
    catalog = client.get("/api/ui/reports").json()
    assert len(catalog) == 1
    assert catalog[0]["origin"] == "published"
    report_id = catalog[0]["id"]
    response = client.get("/api/ui/reports/" + report_id)
    assert response.status_code == 200
    assert response.json()["summary"]["accuracy"] == 100
    assert client.get("/api/ui/reports/published:../../.env").status_code == 404


def test_job_configuration_rejects_untrusted_values():
    from pydantic import ValidationError
    from app.dashboard import EvaluationRequest
    try:
        EvaluationRequest(suite="extended; rm -rf /", mode="standard")
    except ValidationError:
        pass
    else:
        raise AssertionError("Evaluation suite command injection must be rejected")


def test_judge_score_parser():
    output = """Aggregate Metrics
    │ Task Completion           │ 0.99                   │ 100.00% |
    │ Step Efficiency           │ 0.45                   │ 20.00% |
    WARNING: No hyperparameters
    """
    assert dashboard._judge_summary(output) == {"task_completion": 0.99, "step_efficiency":0.45}
