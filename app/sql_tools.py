"""The ONLY module allowed to touch the analytics database.

SQL guard is defense-in-depth: parse SELECT AST, allowlist table names,
connect in DuckDB read-only mode, disable external filesystem/network access.
Educational local application only; not a hardened public SQL sandbox.
"""
import math
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp

from app.settings import database_path

ALLOWED_TABLES = {"customers", "products", "orders", "order_items"}
ALLOWED_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "COALESCE",
    "LOWER", "UPPER", "ABS", "CAST", "TRY_CAST", "DATE_TRUNC",
    "EXTRACT", "YEAR", "MONTH", "NULLIF", "IF", "SUBSTRING",
}
FORBIDDEN_NODES = {
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge",
    "Copy", "Attach", "Detach", "Command", "Set", "Use", "Pragma",
    "Transaction", "Commit", "Rollback", "Grant", "Revoke", "TruncateTable",
}


class UnsafeSQL(ValueError):
    pass


def validate_select(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeSQL("SQL must be a nonempty string")
    if len(sql) > 5000:
        raise UnsafeSQL("SQL too long")
    try:
        expressions = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQL(f"Invalid SQL syntax: {exc}") from exc
    if len(expressions) != 1 or expressions[0] is None:
        raise UnsafeSQL("Exactly one SQL statement is allowed")
    tree = expressions[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise UnsafeSQL("Only SELECT (or SELECT UNION) is permitted")
    for node in tree.walk():
        if type(node).__name__ in FORBIDDEN_NODES:
            raise UnsafeSQL(f"Forbidden SQL operation: {type(node).__name__}")
        if isinstance(node, exp.Func) and not isinstance(
            node, (exp.And, exp.Or, exp.Not)
        ):
            if node.sql_name().upper() not in ALLOWED_FUNCTIONS:
                raise UnsafeSQL(
                    f"Function not allowed: {node.sql_name()}"
                )
    cte_names = {cte.alias.lower() for cte in tree.find_all(exp.CTE) if cte.alias}
    for table in tree.find_all(exp.Table):
        if table.db or table.catalog:
            raise UnsafeSQL("Database-qualified table names are not allowed")
        if table.name.lower() not in ALLOWED_TABLES | cte_names:
            raise UnsafeSQL(f"Unknown/forbidden table: {table.name}")
    # Canonical form removes terminal semicolons and comments.
    return tree.sql(dialect="duckdb")


class SQLTools:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or database_path())

    def _connect(self):
        if not self.db_path.is_file():
            raise FileNotFoundError(f"Database not found: {self.db_path}; run python -m app.seed")
        return duckdb.connect(
            str(self.db_path), read_only=True,
            config={"enable_external_access": "false"},
        )

    def schema(self) -> str:
        """Inspects actual DB structure, not a made-up schema in the prompt."""
        con = self._connect()
        try:
            rows = con.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'main'
                ORDER BY table_name, ordinal_position
            """).fetchall()
        finally:
            con.close()
        return "\n".join(f"{t}.{c}: {kind}" for t, c, kind in rows)

    def execute(self, sql: str) -> dict:
        safe_sql = validate_select(sql)
        con = self._connect()
        try:
            # Fetch at most 50 rows; adding LIMIT to outer SELECT also caps return volume.
            cursor = con.execute(f"SELECT * FROM ({safe_sql}) AS query_result LIMIT 50")
            names = [description[0] for description in cursor.description]
            records = cursor.fetchall()
            rows = []
            for record in records:
                row = {}
                for key, value in zip(names, record):
                    if isinstance(value, float) and not math.isfinite(value):
                        value = None
                    elif hasattr(value, "isoformat"):
                        value = value.isoformat()
                    row[key] = value
                rows.append(row)
            return {"sql": safe_sql, "columns": names, "rows": rows, "returned_rows": len(rows)}
        finally:
            con.close()
