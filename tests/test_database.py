from app.seed import seed
from app.sql_tools import SQLTools


def test_seed_and_queries(tmp_path):
    path = seed(tmp_path / "shop.duckdb")
    db = SQLTools(path)
    assert "customers.customer_id" in db.schema()
    assert db.execute("SELECT COUNT(*) AS n FROM customers")["rows"][0]["n"] == 8
    assert db.execute("SELECT COUNT(*) AS n FROM orders WHERE status='completed'")["rows"][0]["n"] == 14
    revenue_sql = """SELECT SUM(oi.quantity * oi.unit_price) AS revenue
        FROM order_items oi JOIN orders o USING (order_id) WHERE o.status='completed'"""
    total = db.execute(revenue_sql)["rows"][0]["revenue"]
    assert total == 2430.0


def test_result_is_capped(tmp_path):
    db = SQLTools(seed(tmp_path / "shop.duckdb"))
    result = db.execute("SELECT a.customer_id FROM customers a CROSS JOIN customers b")
    assert result["returned_rows"] == 50
