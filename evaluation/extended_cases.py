"""15 additional SQL benchmark cases and independently executable SQL oracles.

Answers are calculated from the seeded synthetic shop data. The SQL in
`reference_sql` is used ONLY for benchmark verification, never as model context.
"""

EXTENDED_CASES = [
    {
        "question": "How many cancelled orders are there?",
        "expected_rows": [[2]],
        "reference_sql": "SELECT COUNT(*) FROM orders WHERE status='cancelled'",
    },
    {
        "question": "How many orders are there in total, including cancelled orders?",
        "expected_rows": [[16]],
        "reference_sql": "SELECT COUNT(*) FROM orders",
    },
    {
        "question": "How many products are in the catalog?",
        "expected_rows": [[5]],
        "reference_sql": "SELECT COUNT(*) FROM products",
    },
    {
        "question": "How many distinct product categories are in the catalog?",
        "expected_rows": [[3]],
        "reference_sql": "SELECT COUNT(DISTINCT category) FROM products",
    },
    {
        "question": "What is the average catalog product price in dollars, rounded to two decimals?",
        "expected_rows": [[86.0]],
        "reference_sql": "SELECT ROUND(AVG(price), 2) FROM products",
    },
    {
        "question": "What was completed-order revenue during January 2025?",
        "expected_rows": [[350.0]],
        "reference_sql": """SELECT SUM(oi.quantity * oi.unit_price)
            FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
            WHERE o.status='completed'
              AND o.order_date >= '2025-01-01' AND o.order_date < '2025-02-01'""",
    },
    {
        "question": "What was completed-order revenue during February 2025?",
        "expected_rows": [[365.0]],
        "reference_sql": """SELECT SUM(oi.quantity * oi.unit_price)
            FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
            WHERE o.status='completed'
              AND o.order_date >= '2025-02-01' AND o.order_date < '2025-03-01'""",
    },
    {
        "question": "What is Ava's total revenue from completed orders?",
        "expected_rows": [[415.0]],
        "reference_sql": """SELECT SUM(oi.quantity * oi.unit_price)
            FROM customers c JOIN orders o ON o.customer_id=c.customer_id
            JOIN order_items oi ON oi.order_id=o.order_id
            WHERE c.name='Ava' AND o.status='completed'""",
    },
    {
        "question": "What is George's total revenue from completed orders?",
        "expected_rows": [[505.0]],
        "reference_sql": """SELECT SUM(oi.quantity * oi.unit_price)
            FROM customers c JOIN orders o ON o.customer_id=c.customer_id
            JOIN order_items oi ON oi.order_id=o.order_id
            WHERE c.name='George' AND o.status='completed'""",
    },
    {
        "question": "How many units of the Monitor product were sold in completed orders?",
        "expected_rows": [[6]],
        "reference_sql": """SELECT SUM(oi.quantity)
            FROM order_items oi JOIN orders o ON o.order_id=oi.order_id
            JOIN products p ON p.product_id=oi.product_id
            WHERE o.status='completed' AND p.name='Monitor'""",
    },
    {
        "question": "How many distinct customers placed a completed order?",
        "expected_rows": [[8]],
        "reference_sql": "SELECT COUNT(DISTINCT customer_id) FROM orders WHERE status='completed'",
    },
    {
        "question": "What is the average revenue per completed order, rounded to two decimal places?",
        "expected_rows": [[173.57]],
        "reference_sql": """WITH totals AS (
            SELECT o.order_id, SUM(oi.quantity * oi.unit_price) AS revenue
            FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
            WHERE o.status='completed' GROUP BY o.order_id
        ) SELECT ROUND(AVG(revenue), 2) FROM totals""",
    },
    {
        "question": "Show the number of orders for each status, sorted alphabetically by status.",
        "expected_rows": [["cancelled", 2], ["completed", 14]],
        "reference_sql": "SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status ASC",
        "fields": [("status", "order_status"),
                   ("order_count", "orders_count", "number_of_orders", "count", "total_orders", "num_orders", "count_star")],
    },
    {
        "question": "Show total revenue from completed orders by product category, highest revenue first.",
        "expected_rows": [["Displays", 1320.0], ["Accessories", 785.0], ["Video", 325.0]],
        "reference_sql": """SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
            FROM products p JOIN order_items oi ON p.product_id=oi.product_id
            JOIN orders o ON o.order_id=oi.order_id WHERE o.status='completed'
            GROUP BY p.category ORDER BY revenue DESC, p.category ASC""",
        "fields": [("category", "product_category", "category_name"),
                   ("total_revenue", "completed_revenue", "revenue", "category_revenue")],
    },
    {
        "question": "Show the three most expensive products by current catalog price, descending by price.",
        "expected_rows": [["Monitor", 220.0], ["Keyboard", 80.0], ["Webcam", 65.0]],
        "reference_sql": "SELECT name, price FROM products ORDER BY price DESC, name ASC LIMIT 3",
        "fields": [("name", "product_name"),
                   ("price", "product_price", "catalog_price", "unit_price")],
    },
]
