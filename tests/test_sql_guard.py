import pytest
from app.sql_tools import UnsafeSQL, validate_select

@pytest.mark.parametrize("query", [
    "DELETE FROM customers",
    "DROP TABLE orders",
    "UPDATE products SET price = 0",
    "SELECT * FROM customers; DELETE FROM orders",
    "SELECT * FROM secrets",
    "SELECT * FROM read_csv_auto('/tmp/private.csv')",
    "ATTACH '/tmp/other.duckdb' AS other",
    "CREATE TABLE evil AS SELECT * FROM customers",
    "SELECT * FROM other.customers",
])
def test_unsafe_queries_blocked(query):
    with pytest.raises(UnsafeSQL):
        validate_select(query)

@pytest.mark.parametrize("query", [
    "SELECT COUNT(*) AS n FROM customers",
    "SELECT c.name FROM customers c ORDER BY c.name LIMIT 3",
    "SELECT SUM(oi.quantity * oi.unit_price) AS revenue FROM order_items oi",
    "WITH x AS (SELECT customer_id FROM customers) SELECT COUNT(*) FROM x",
])
def test_safe_queries_allowed(query):
    assert validate_select(query).upper().startswith(("SELECT", "WITH"))

@pytest.mark.parametrize("query", [
    """
    SELECT * FROM orders
    WHERE status = 'completed'
      AND order_date >= '2025-01-01'
    """,
    """
    SELECT * FROM orders
    WHERE status = 'completed'
       OR status = 'cancelled'
    """,
    """
    SELECT * FROM orders
    WHERE NOT status = 'cancelled'
    """,
])
def test_logical_operators_allowed(query):
    assert validate_select(query)


def test_unsafe_functions_still_blocked():
    with pytest.raises(UnsafeSQL):
        validate_select(
            "SELECT read_csv_auto('/tmp/private.csv')"
        )