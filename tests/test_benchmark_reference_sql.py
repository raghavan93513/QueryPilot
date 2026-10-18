"""Verify every reference answer against the actual seeded DuckDB database."""
import pytest
from app.seed import seed
from evaluation.scoring import normalized_rows
from evaluation.extended_cases import EXTENDED_CASES
from app.sql_tools import SQLTools


@pytest.mark.parametrize("case", EXTENDED_CASES, ids=lambda c: c["question"])
def test_reference_answers(case, tmp_path):
    db = SQLTools(seed(tmp_path / "shop.duckdb"))
    result = db.execute(case["reference_sql"])
    actual = normalized_rows([list(row.values()) for row in result["rows"]])
    expected = normalized_rows(case["expected_rows"])
    assert actual == expected
