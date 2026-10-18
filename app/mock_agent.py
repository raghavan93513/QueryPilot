"""Predictable SQL generator ONLY for tests and smoke demos (not AI)."""

def generate_mock_sql(question: str, schema: str, error: str = "", previous_sql: str = "") -> str:
    q = question.lower()
    if "inject" in q:
        return "DELETE FROM customers"  # Used to verify authorization cannot bypass validation.
    if "repair" in q and not error:
        return "SELECT nonexistent_column FROM customers"
    if "repair" in q:
        return "SELECT COUNT(*) AS customer_count FROM customers"
    if "how many customers" in q or "count customers" in q:
        return "SELECT COUNT(*) AS customer_count FROM customers"
    if "how many completed orders" in q or "count completed orders" in q:
        return "SELECT COUNT(*) AS completed_orders FROM orders WHERE status='completed'"
    if "top" in q and "customer" in q:
        return """SELECT c.name, SUM(oi.quantity * oi.unit_price) AS revenue
            FROM customers c JOIN orders o ON c.customer_id=o.customer_id
            JOIN order_items oi ON oi.order_id=o.order_id
            WHERE o.status='completed'
            GROUP BY c.customer_id, c.name ORDER BY revenue DESC, c.name LIMIT 5"""
    if "by product" in q or "per product" in q:
        return """SELECT p.name AS product, SUM(oi.quantity*oi.unit_price) AS revenue
            FROM order_items oi JOIN products p ON oi.product_id=p.product_id
            JOIN orders o ON oi.order_id=o.order_id WHERE o.status='completed'
            GROUP BY p.product_id,p.name ORDER BY revenue DESC, p.name"""
    if "total revenue" in q or "completed revenue" in q:
        return """SELECT SUM(oi.quantity*oi.unit_price) AS total_revenue
            FROM order_items oi JOIN orders o ON oi.order_id=o.order_id
            WHERE o.status='completed'"""
    return "SELECT COUNT(*) AS customer_count FROM customers"
