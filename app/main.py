"""FastAPI application. Run locally via uvicorn app.main:app --reload."""
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from langgraph.types import Command

from app.workflow import create_workflow, config_for, current_view
from app.dashboard import mount_dashboard


class NewRun(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Approval(BaseModel):
    approved: bool
    feedback: str = Field(default="", max_length=1000)


def build_api(graph=None):
    app = FastAPI(title="Self-Correcting SQL Analytics Agent", version="1.0")
    workflow = graph or create_workflow()

    @app.get("/health")
    def health():
        return {"status": "ok", "note": "This does not test model availability"}

    @app.post("/runs")
    def create_run(request: NewRun):
        run_id = str(uuid4())
        try:
            workflow.invoke({
                "question": request.question,
                "attempts": 0,
                "tool_calls": [],
                "status": "started",
            }, config=config_for(run_id))
        except Exception as exc:
            # Report model/database failures (never claim a completed run).
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return current_view(workflow, run_id)

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        try:
            return current_view(workflow, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown run") from exc

    @app.post("/runs/{run_id}/resume")
    def resume_run(run_id: str, request: Approval):
        try:
            view = current_view(workflow, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown run") from exc
        if view["status"] != "awaiting_approval":
            raise HTTPException(status_code=409, detail="Run is not awaiting approval")
        try:
            workflow.invoke(
                Command(resume={"approved": request.approved, "feedback": request.feedback}),
                config=config_for(run_id),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return current_view(workflow, run_id)

    mount_dashboard(app, workflow)
    return app


app = build_api()
