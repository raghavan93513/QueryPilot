"""Benchmark actual graph runs with reference answers + DeepEval ToolCorrectness.

Default: reference-answer checks and DeepEval tool correctness.
Optional: --llm-judge runs DeepEval trace metrics using configured judge.
Auto-approval is used ONLY for this trusted, isolated sample dataset.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from deepeval.metrics import ToolCorrectnessMetric, TaskCompletionMetric, StepEfficiencyMetric
from deepeval.test_case import LLMTestCase, ToolCall
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.tracing import observe, update_current_trace
from deepeval.evaluate import AsyncConfig
from langgraph.types import Command

from app.seed import seed
from app.sql_tools import SQLTools
from evaluation.traced_tools import TracedSQLTools
from evaluation.scoring import normalized_rows, is_correct
from evaluation.extended_cases import EXTENDED_CASES
from evaluation.workflow_policy import judge_trace_input, schema_policy_observed
from evaluation.agent_runtime import evaluation_generator
from app.settings import database_path, ROOT
from app.workflow import create_workflow, config_for, current_view
from app.run_history import snapshot_timeline

CASES = [
    {"question": "How many customers are there?", "expected_rows": [[8]]},
    {"question": "How many completed orders are there?", "expected_rows": [[14]]},
    {"question": "What is the total revenue from completed orders?", "expected_rows": [[2430.0]]},
    {
        "question": "Show the top five customers by completed revenue",
        "expected_rows": [["George", 505.0], ["Ava", 415.0], ["Hana", 390.0],
                          ["Ben", 380.0], ["Daniel", 220.0]],
        "alternative_expected_rows": [[
            ["George", 505.0], ["Ava", 415.0], ["Hana", 390.0],
            ["Ben", 380.0], ["Farah", 220.0],
        ]],
        "fields": [("name", "customer_name"),
                   ("completed_revenue", "total_revenue", "revenue")],
    },
    {
        "question": "Show completed revenue by product",
        "expected_rows": [["Monitor", 1320.0], ["Keyboard", 400.0],
                          ["Webcam", 325.0], ["Mouse", 225.0], ["Laptop Stand", 160.0]],
        "fields": [("product_name", "name"),
                   ("completed_revenue", "total_revenue", "revenue")],
        "unordered": True,
    },
]


def run_one(graph, question):
    """Run one trusted sample question, resuming its HITL checkpoints.

    DeepEval @observe spans around the outer agent and the SQL tools handle
    tracing. Do not attach a CallbackHandler to every interrupted invocation:
    a callback-created root trace can remain unfinished at interrupt().
    """
    run_id = str(uuid4())

    def invoke(payload):
        # Keep the same thread_id for each interrupt()/resume transition.
        # DeepEval's outer @observe records the overall run; manual @observe
        # wrappers record AutoGen generation and SQL tools.
        return graph.invoke(payload, config_for(run_id))

    invoke({"question": question, "attempts": 0, "tool_calls": []})
    view = current_view(graph, run_id)
    while view["status"] == "awaiting_approval":
        invoke(Command(resume={"approved": True, "feedback": ""}))
        view = current_view(graph, run_id)
    return view


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("baseline", "extended"), default="baseline",
                        help="Use 5-question baseline or 20-question expanded benchmark")
    parser.add_argument(
        "--judge-policy", choices=("raw", "schema-required"), default="raw",
        help="Trace-only judging task: raw question or explicit schema-first "
             "workflow constraints; scores across modes are not directly comparable",
    )
    parser.add_argument("--output", type=Path, default=None,
                        help="Save benchmark JSON in reports/generated/ unless overridden")
    parser.add_argument("--trace-output", type=Path, default=None,
                        help="Save advanced checkpoint histories under reports/generated/")
    parser.add_argument("--llm-judge", action="store_true",
                        help="Extra DeepEval LLM-judge trajectory metrics")
    parser.add_argument("--judge-only", action="store_true",
                        help="Skip the standard benchmark; debug tracing/judging alone")
    parser.add_argument("--judge-limit", type=int, default=5,
                        help="Number of questions to judge (default 5)")
    args = parser.parse_args()
    global CASES
    if args.suite == "extended":
        CASES = CASES + EXTENDED_CASES
    if args.judge_policy != "raw" and not args.llm_judge:
        parser.error("--judge-policy schema-required requires --llm-judge")
    if args.judge_only and not args.llm_judge:
        parser.error("--judge-only requires --llm-judge")
    if not 1 <= args.judge_limit <= len(CASES):
        parser.error(f"--judge-limit must be between 1 and {len(CASES)}")
    if not database_path().exists():
        seed()

    # SQL proposals are still generated by the same AutoGen agents. Only their
    # evaluation-time event-loop lifecycle changes; production API is unchanged.
    with evaluation_generator(trace_enabled=args.llm_judge) as generator:
        graph = create_workflow(
            db=TracedSQLTools(SQLTools()) if args.llm_judge else None,
            generator=generator,
            checkpoint_file=ROOT / "data" / "eval_checkpoints.sqlite",
        )
        if not args.judge_only:
            passed = 0
            report = []
            metric = ToolCorrectnessMetric(threshold=1.0)
            for case in CASES:
                view = run_one(graph, case["question"])
                rows = view.get("rows") or []
                correct = is_correct(case, rows, status=view["status"])
                tools = [ToolCall(name=name) for name in view["tool_calls"]]
                test_case = LLMTestCase(
                    input=case["question"], actual_output=json.dumps(rows, default=str),
                    tools_called=tools,
                    expected_tools=[ToolCall(name="inspect_schema"), ToolCall(name="execute_sql")],
                )
                metric.measure(test_case)
                result = {
                    "question": case["question"], "passed": bool(correct),
                    "expected_rows": case["expected_rows"], "actual_rows": rows,
                    "attempts": view["attempts"], "tool_correctness": metric.score,
                    "schema_verified_once": schema_policy_observed(view["tool_calls"]),
                    "status": view["status"],
                }
                result['trace'] = snapshot_timeline(graph, view['run_id'])
                print(json.dumps(result), flush=True)
                report.append(result)
                passed += bool(correct)
            report_path = args.output or ROOT / "reports" / "generated" / f"benchmark_{args.suite}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"\nExact result accuracy: {passed}/{len(CASES)} "
                  f"({100*passed/len(CASES):.0f}%)")
            print(f"Saved report to {report_path}")
            print(f"Average attempts: {sum(r['attempts'] for r in report) / len(report):.2f}")

        if args.llm_judge:
            advanced_report = []
            @observe(type="agent", name="sql_analytics_full_workflow")
            def traced_agent(question: str):
                # Avoid per-invocation CallbackHandler here: interrupt/resume
                # can leave separate callback-created traces unfinished.
                # Manual spans still cover SQL tools and AutoGen collaboration.
                result = run_one(graph, question)
                answer = json.dumps(result.get("rows", []), default=str)
                matching_case = next(c for c in CASES if c['question'] == question)
                advanced_report.append({
                    'question': question,
                    'passed': bool(is_correct(matching_case, result.get('rows') or [], status=result['status'])),
                    'expected_rows': matching_case['expected_rows'],
                    'actual_rows': result.get('rows') or [],
                    'attempts': result.get('attempts', 0),
                    'schema_verified_once': schema_policy_observed(result.get('tool_calls', [])),
                    'status': result['status'],
                    'judge_policy': args.judge_policy,
                    'trace': snapshot_timeline(graph, result['run_id']),
                })
                # Trace-only task framing. The real SQL agent still receives
                # only the user's question, not the evaluation policy text.
                # Do not compare raw and policy-conditioned scores as identical
                # benchmark metrics: the task definitions differ.
                update_current_trace(
                    input=judge_trace_input(question, args.judge_policy),
                    output=answer,
                    tools_called=[ToolCall(name=n) for n in result["tool_calls"]],
                    metadata={
                        "original_question": question,
                        "judge_policy": args.judge_policy,
                        "schema_verified_once": schema_policy_observed(result["tool_calls"]),
                        "sql_attempts": result["attempts"],
                    },
                )
                return answer

            dataset = EvaluationDataset(
                goldens=[Golden(input=c["question"]) for c in CASES[:args.judge_limit]]
            )
            for golden in dataset.evals_iterator(
                metrics=[
                    TaskCompletionMetric(threshold=0.7),
                    StepEfficiencyMetric(threshold=0.7),
                ],
                async_config=AsyncConfig(run_async=False),
            ):
                print(f"Starting traced evaluation [{args.judge_policy}]: "
                      f"{golden.input}", flush=True)
                traced_agent(golden.input)
                print("Traced graph finished; awaiting judge scoring.", flush=True)
            trace_path = args.trace_output or ROOT / 'reports' / 'generated' / f'advanced_traces_{args.suite}.json'
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(json.dumps(advanced_report, indent=2), encoding='utf-8')


if __name__ == "__main__":
    main()
