"""Local-only web workspace, evaluation reports, and benchmark launcher.

There is deliberately no shell execution or externally supplied command text.
Run Uvicorn on 127.0.0.1:8000, never on a public interface without auth.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.run_history import snapshot_timeline
from app.settings import ROOT

WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
MAX_JSON_BYTES = 5_000_000


class EvaluationRequest(BaseModel):
    suite: str = Field(default="extended", pattern="^(baseline|extended)$")
    mode: str = Field(default="standard", pattern="^(standard|advanced)$")
    judge_limit: int = Field(default=5, ge=1, le=20)
    judge_policy: str = Field(default="schema-required", pattern="^(raw|schema-required)$")


def _report_paths() -> dict[str, Path]:
    """Published and generated benchmarks both live under reports/."""
    paths = {}
    for origin, folder in (("published", REPORTS_DIR), ("generated", REPORTS_DIR / "generated")):
        if not folder.exists():
            continue
        for path in folder.glob("benchmark_*.json"):
            if path.is_file() and path.stat().st_size <= MAX_JSON_BYTES:
                paths[f"{origin}:{path.name}"] = path
    return paths


def _read_report(path: Path) -> list[dict] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError, OSError):
        return None
    if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
        return None
    if not all("question" in x and "passed" in x for x in value):
        return None
    return value


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    completed = sum(r.get("status") == "completed" for r in rows)
    passed = sum(r.get("passed") is True for r in rows)
    attempts = [int(r.get("attempts") or 0) for r in rows]
    tool_scores = [float(r["tool_correctness"]) for r in rows if isinstance(r.get("tool_correctness"), (int, float))]
    verified = [r.get("schema_verified_once") for r in rows if "schema_verified_once" in r]
    return {
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total * 100, 1) if total else 0,
        "completed": completed,
        "first_try": sum(bool(r.get("passed")) and r.get("attempts") == 1 for r in rows),
        "average_attempts": round(sum(attempts) / total, 2) if total else 0,
        "tool_correctness": round(sum(tool_scores) / len(tool_scores), 3) if tool_scores else None,
        "schema_verified": sum(v is True for v in verified) if verified else None,
        "schema_sample_size": len(verified),
        "traced_cases": sum(isinstance(r.get("trace"), list) and len(r["trace"]) > 0 for r in rows),
    }


def report_catalog() -> list[dict]:
    candidates = []
    for report_id, path in _report_paths().items():
        rows = _read_report(path)
        if rows is None:
            continue
        candidates.append({
            "id": report_id,
            "name": path.name,
            "origin": report_id.split(":", 1)[0],
            "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "summary": summarize(rows),
        })
    return sorted(candidates, key=lambda r: r["modified"], reverse=True)


def _tail(path: Path, max_bytes: int = 16000) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - max_bytes))
            result = stream.read().decode("utf-8", errors="replace")
        return re.sub(r"\x1b\[[0-9;]*m", "", result)
    except OSError:
        return ""


def _judge_summary(text: str) -> dict:
    """Best-effort extraction of displayed aggregates; never invent a score."""
    if "Aggregate Metrics" not in text:
        return {}
    section = text.split("Aggregate Metrics")[-1].split("WARNING:")[0]
    found = {}
    for label, key in (("Task Completion", "task_completion"), ("Step Efficiency", "step_efficiency")):
        match = re.search(re.escape(label) + r"\s*[│|]\s*([0-9]+(?:\.[0-9]+)?)", section)
        if match:
            found[key] = float(match.group(1))
    return found


class EvalJobManager:
    """One local benchmark process at a time, with inspectable logs."""
    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._job = None
        self._log_handle = None

    def start(self, request: EvaluationRequest) -> dict:
        with self._lock:
            if self._process and self._process.poll() is None:
                raise HTTPException(status_code=409, detail="An evaluation is already running")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (REPORTS_DIR / "generated").mkdir(parents=True, exist_ok=True)
            jobs_dir = DATA_DIR / "ui_jobs"
            jobs_dir.mkdir(parents=True, exist_ok=True)
            job_id = str(uuid4())
            log_path = jobs_dir / f"{job_id}.log"
            output_path = REPORTS_DIR / "generated" / f"benchmark_{request.suite}_{job_id}.json"
            command = [sys.executable, "-u", "-m", "evaluation.run_eval", "--suite", request.suite,
                       "--output", str(output_path)]
            if request.mode == "advanced":
                limit = min(request.judge_limit, 5 if request.suite == "baseline" else 20)
                trace_path = REPORTS_DIR / "generated" / f"advanced_traces_{job_id}.json"
                command += ["--llm-judge", "--judge-only", "--judge-limit", str(limit),
                            "--judge-policy", request.judge_policy,
                            "--trace-output", str(trace_path)]
            self._log_handle = log_path.open("w", encoding="utf-8")
            try:
                self._process = subprocess.Popen(
                    command, cwd=str(ROOT), env=os.environ.copy(),
                    stdout=self._log_handle, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                )
            except Exception:
                self._log_handle.close()
                self._log_handle = None
                raise
            self._job = {
                "id": job_id, "state": "running", "suite": request.suite,
                "mode": request.mode, "judge_policy": request.judge_policy,
                "started": datetime.now(timezone.utc).isoformat(),
                "log_path": log_path,
                "exit_code": None, "finished": None,
            }
            return self.status()

    def status(self) -> dict:
        # Called only from local endpoints. Poll to refresh completion state.
        job = self._job
        if not job:
            return {"state": "idle", "log": ""}
        if job["state"] == "running" and self._process is not None:
            exit_code = self._process.poll()
            if exit_code is not None:
                job["exit_code"] = exit_code
                job["state"] = "completed" if exit_code == 0 else "failed"
                job["finished"] = datetime.now(timezone.utc).isoformat()
                if self._log_handle:
                    self._log_handle.close()
                    self._log_handle = None
                if job["mode"] == "advanced":
                    details = _judge_summary(_tail(job["log_path"], 100000))
                    if details:
                        out = REPORTS_DIR / "generated" / "judge_summary.json"
                        out.write_text(json.dumps({
                            "source": "DeepEval console aggregate (best-effort parser)",
                            "suite": job["suite"], "judge_policy": job["judge_policy"],
                            "completed_at": job["finished"], **details,
                        }, indent=2), encoding="utf-8")
        return {
            **{k: v for k, v in job.items() if k != "log_path"},
            "log": _tail(job["log_path"]),
        }


job_manager = EvalJobManager()


def _local_only(request: Request):
    """Second-line guard for local development endpoints."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="The dashboard is local-only")


def mount_dashboard(app: FastAPI, workflow):
    if not WEB_DIR.is_dir():
        # Make missing assets a visible setup error rather than a server crash.
        @app.get("/")
        def missing_frontend():
            return {"message": "Frontend not installed; copy web/ into the project"}
        return

    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="sql_agent_assets")

    @app.get("/", include_in_schema=False)
    @app.get("/app", include_in_schema=False)
    def homepage(request: Request):
        _local_only(request)
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/ui/runs/{run_id}/trace")
    def run_trace(run_id: str, request: Request):
        _local_only(request)
        # Raises 404 for unknown thread, matching GET /runs/{run_id} semantics.
        from app.workflow import current_view
        try:
            current_view(workflow, run_id)
            events = snapshot_timeline(workflow, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown run") from exc
        return {"run_id": run_id, "kind": "langgraph_checkpoints", "events": events}

    @app.get("/api/ui/reports")
    def list_reports(request: Request):
        _local_only(request)
        return report_catalog()

    @app.get("/api/ui/reports/{report_id}")
    def report_detail(report_id: str, request: Request):
        _local_only(request)
        selected = _report_paths().get(report_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="Report not found")
        rows = _read_report(selected)
        if rows is None:
            raise HTTPException(status_code=422, detail="Not a benchmark report")
        return {"id": report_id, "name": selected.name, "summary": summarize(rows), "cases": rows,
                "trace_kind": "langgraph_checkpoints"}

    @app.get("/api/ui/judge-summary")
    def judge_summary(request: Request):
        _local_only(request)
        path = REPORTS_DIR / "generated" / "judge_summary.json"
        if not path.exists():
            path = REPORTS_DIR / "judge_summary.json"
        if not path.exists():
            return {"available": False}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"available": False}
        return {"available": True, **data}

    @app.get("/api/ui/evaluation-job")
    def evaluation_job(request: Request):
        _local_only(request)
        return job_manager.status()

    @app.post("/api/ui/evaluation-job")
    def launch_evaluation(request: Request, spec: EvaluationRequest):
        _local_only(request)
        return job_manager.start(spec)
