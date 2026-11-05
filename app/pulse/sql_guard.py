from __future__ import annotations

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"pr_metrics", "issue_metrics", "open_work", "workload", "commits"}

FORBIDDEN_FUNCTION_PREFIXES = (
    "pg_", "lo_", "dblink", "set_config", "current_setting", "query_to_xml",
    "table_to_xml", "cursor_to_xml", "xpath", "txid_", "nextval", "setval",
)

FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Into, exp.Lock, exp.Copy, exp.TruncateTable, exp.Grant,
)

MAX_ROWS = 200


class UnsafeSQLError(ValueError):
    """The SQL is not allowed to run. The message is safe to show to the user and the LLM."""


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return node.sql_name().lower()


def validate_sql(sql: str, max_rows: int = MAX_ROWS) -> str:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise UnsafeSQLError("Empty query.")

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQLError(f"Could not parse SQL: {exc}") from exc

    if len(statements) != 1:
        raise UnsafeSQLError("Exactly one statement is allowed.")
    stmt = statements[0]

    if not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise UnsafeSQLError(f"Only SELECT queries are allowed (got {stmt.key.upper()}).")

    for node in stmt.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQLError(f"{node.key.upper()} is not allowed.")

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        name = table.name.lower()
        schema = table.db.lower()
        if schema not in ("", "public") or table.catalog:
            raise UnsafeSQLError(f"Schema '{table.db}' is not allowed.")
        if name not in ALLOWED_TABLES and name not in cte_names:
            allowed = ", ".join(sorted(ALLOWED_TABLES))
            raise UnsafeSQLError(f"Table '{name or table.sql()}' is not allowed. Use only: {allowed}.")

    for func in stmt.find_all(exp.Func):
        name = _function_name(func)
        if name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
            raise UnsafeSQLError(f"Function '{name}' is not allowed.")

    inner = stmt.sql(dialect="postgres")
    return f"SELECT * FROM ({inner}) AS q LIMIT {int(max_rows)}"
