"""Generate a small, deterministic fictional retail database. No external data needed."""
import duckdb
from app.settings import database_path

CUSTOMERS = [
    (1, "Ava", "New York"), (2, "Ben", "Boston"),
    (3, "Chloe", "Chicago"), (4, "Daniel", "Seattle"),
    (5, "Eva", "Austin"), (6, "Farah", "Miami"),
    (7, "George", "Denver"), (8, "Hana", "San Francisco"),
]
PRODUCTS = [
    (1, "Keyboard", "Accessories", 80.0),
    (2, "Mouse", "Accessories", 25.0),
    (3, "Monitor", "Displays", 220.0),
    (4, "Laptop Stand", "Accessories", 40.0),
    (5, "Webcam", "Video", 65.0),
]
ORDERS = [
    (1, 1, "2025-01-05", "completed"), (2, 2, "2025-01-07", "completed"),
    (3, 3, "2025-02-04", "completed"), (4, 1, "2025-02-15", "completed"),
    (5, 4, "2025-02-20", "cancelled"), (6, 2, "2025-03-03", "completed"),
    (7, 5, "2025-03-10", "completed"), (8, 6, "2025-03-19", "completed"),
    (9, 7, "2025-04-02", "completed"), (10, 8, "2025-04-12", "completed"),
    (11, 3, "2025-04-18", "completed"), (12, 4, "2025-05-07", "completed"),
    (13, 5, "2025-05-10", "cancelled"), (14, 6, "2025-05-18", "completed"),
    (15, 7, "2025-06-02", "completed"), (16, 8, "2025-06-14", "completed"),
]
# order_id, product_id, quantity, unit_price_at_purchase
ITEMS = [
    (1,1,1,80.0), (1,2,2,25.0), (2,3,1,220.0), (3,4,2,40.0),
    (4,3,1,220.0), (4,5,1,65.0), (5,3,1,220.0), (6,1,2,80.0),
    (7,5,2,65.0), (8,2,4,25.0), (9,3,2,220.0),
    (10,4,1,40.0), (10,1,1,80.0), (11,5,1,65.0), (11,2,1,25.0),
    (12,3,1,220.0), (13,1,3,80.0), (14,1,1,80.0),
    (14,4,1,40.0), (15,5,1,65.0), (16,3,1,220.0), (16,2,2,25.0),
]


def seed(path=None):
    path = path or database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Re-create intentionally. Never use this against a real user's database.
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name VARCHAR, city VARCHAR)")
        con.execute("CREATE TABLE products (product_id INTEGER PRIMARY KEY, name VARCHAR, category VARCHAR, price DOUBLE)")
        con.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, order_date DATE, status VARCHAR)")
        con.execute("CREATE TABLE order_items (order_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price DOUBLE)")
        con.executemany("INSERT INTO customers VALUES (?, ?, ?)", CUSTOMERS)
        con.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", PRODUCTS)
        con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", ORDERS)
        con.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?)", ITEMS)
    finally:
        con.close()
    return path


if __name__ == "__main__":
    print(f"Created sample database: {seed()}")
