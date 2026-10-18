"""Dependency-free benchmark answer scoring.

Scores the columns requested by each question, rather than every optional ID.
Order is compared only for explicitly ranked questions. Cases may provide
alternative_expected_rows when a query has genuine ties at a LIMIT boundary.
"""


def normalized_rows(rows, fields=None):
    """Normalize values for stable comparison across numeric SQL types and aliases."""
    def norm(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return ("num", round(float(value), 2))
        return ("text", str(value).strip().casefold())

    normalized = []
    for row in rows:
        if isinstance(row, dict):
            lower = {str(k).lower(): v for k, v in row.items()}
            if fields is None:
                if len(lower) != 1:
                    return None
                values = list(lower.values())
            else:
                values = []
                for aliases in fields:
                    key = next((alias for alias in aliases if alias in lower), None)
                    if key is None:
                        return None
                    values.append(lower[key])
        else:
            values = list(row)
        normalized.append(tuple(norm(v) for v in values))
    return normalized


def is_correct(case, actual_rows, status="completed"):
    """Compare actual rows against each valid answer, preserving order where needed.

    Alternative expected answers are narrowly specified for legitimate boundary
    ties. They must not be used to excuse wrong joins or calculations.
    """
    if status != "completed":
        return False
    actual = normalized_rows(actual_rows, case.get("fields"))
    if actual is None:
        return False
    if case.get("unordered", False):
        actual = sorted(actual)

    candidates = [case["expected_rows"], *case.get("alternative_expected_rows", [])]
    for expected_rows in candidates:
        expected = normalized_rows(expected_rows)
        if expected is None:
            continue
        if case.get("unordered", False):
            expected = sorted(expected)
        if actual == expected:
            return True
    return False
