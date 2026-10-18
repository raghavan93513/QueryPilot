"""Optional DeepEval spans around the SQL tools that really do I/O.

These wrappers are used by the evaluation script only. They do not change the
SQL guard or execute additional queries; they delegate directly to SQLTools.
"""
import json

from deepeval.tracing import observe, update_current_span


class TracedSQLTools:
    def __init__(self, underlying):
        self._underlying = underlying

    @observe(type="tool", name="inspect_schema")
    def schema(self):
        schema = self._underlying.schema()
        update_current_span(input="Inspect allowed database schema", output=schema)
        return schema

    @observe(type="tool", name="execute_sql")
    def execute(self, sql):
        result = self._underlying.execute(sql)
        # Log only query + result size by default, not full rows, so this
        # remains appropriate when adapting to private databases later.
        update_current_span(
            input=sql,
            output=json.dumps({
                "columns": result["columns"], "row_count": len(result["rows"]),
            }),
        )
        return result
