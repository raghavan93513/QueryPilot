"""Score correctness checks do not call DeepEval or Ollama."""

from evaluation.scoring import is_correct
from evaluation.extended_cases import EXTENDED_CASES


def test_equal_revenue_ties_are_legitimate_alternatives():
    case = {
        "expected_rows": [["George", 505], ["Daniel", 220]],
        "alternative_expected_rows": [[["George", 505], ["Farah", 220]]],
        "fields": [("name",), ("revenue",)],
    }
    assert is_correct(case, [{"name": "George", "revenue": 505},
                             {"name": "Daniel", "revenue": 220}])
    assert is_correct(case, [{"name": "George", "revenue": 505},
                             {"name": "Farah", "revenue": 220}])
    assert not is_correct(case, [{"name": "George", "revenue": 505},
                                 {"name": "Farah", "revenue": 999}])


def test_ranked_results_must_keep_the_rank():
    case = EXTENDED_CASES[-1]
    rows = [{"product_name": name, "price": price} for name, price in case["expected_rows"]]
    assert is_correct(case, rows)
    assert not is_correct(case, list(reversed(rows)))


def test_one_number_response_and_failed_status():
    case = EXTENDED_CASES[0]
    assert is_correct(case, [{"cancelled_orders": 2}])
    assert not is_correct(case, [{"cancelled_orders": 3}])
    assert not is_correct(case, [{"cancelled_orders": 2}], "failed")


def test_required_columns_cannot_be_missing():
    case = EXTENDED_CASES[-2]
    wrong = [{"category": name, "irrelevant": value} for name, value in case["expected_rows"]]
    assert not is_correct(case, wrong)


def test_all_new_benchmark_questions_are_distinct_and_have_oracle_sql():
    assert len(EXTENDED_CASES) == 15
    assert len({case["question"] for case in EXTENDED_CASES}) == 15
    assert all("reference_sql" in case for case in EXTENDED_CASES)
