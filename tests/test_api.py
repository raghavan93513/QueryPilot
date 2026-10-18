from fastapi.testclient import TestClient
from app.main import build_api
from app.workflow import create_workflow
from app.seed import seed
from app.sql_tools import SQLTools
from app.mock_agent import generate_mock_sql


def test_http_approval_and_resume(tmp_path):
    graph = create_workflow(
        db=SQLTools(seed(tmp_path / "shop.duckdb")),
        generator=generate_mock_sql,
        checkpoint_file=tmp_path / "cp.sqlite",
    )
    client = TestClient(build_api(graph))
    assert client.get("/health").status_code == 200
    response = client.post("/runs", json={"question": "How many customers?"})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "awaiting_approval"
    assert client.get("/runs/" + run["run_id"]).json()["status"] == "awaiting_approval"
    done = client.post("/runs/" + run["run_id"] + "/resume", json={"approved": True})
    assert done.status_code == 200, done.text
    assert done.json()["rows"][0]["customer_count"] == 8
    assert client.post("/runs/" + run["run_id"] + "/resume", json={"approved": True}).status_code == 409
