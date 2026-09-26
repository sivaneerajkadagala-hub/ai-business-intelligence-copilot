"""AST-level SQL validation via sqlglot.

Every candidate query — LLM or rule engine — must pass through here
before execution. Only SELECT statements over whitelisted dataset tables
and columns survive; a LIMIT is enforced. No exceptions."""

import sqlglot
from sqlglot import exp

FORBIDDEN_EXPRESSIONS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
    exp.TruncateTable, exp.Create, exp.Merge, exp.Copy, exp.Command,
)

DANGEROUS_FUNCTIONS = {
    "pg_sleep", "pg_read_file", "pg_ls_dir", "pg_write_file",
    "lo_import", "lo_export", "xp_cmdshell", "load_extension",
    "writefile", "readfile", "pragma",
}

DEFAULT_ROW_CAP = 5000


class SQLValidationError(ValueError):
    pass


def validate(
    sql: str,
    *,
    allowed_tables: set[str],
    allowed_columns: set[str],
    dialect: str,
    row_cap: int = DEFAULT_ROW_CAP,
) -> str:
    """Returns a safe, LIMIT-enforced SQL string or raises SQLValidationError."""
    try:
        parsed = sqlglot.parse(sql, read=dialect)
    except Exception as e:
        raise SQLValidationError(f"Unparseable SQL: {e}") from e

    parsed = [s for s in parsed if s is not None]
    if len(parsed) != 1:
        raise SQLValidationError("Exactly one statement is allowed")

    stmt = parsed[0]
    if not isinstance(stmt, exp.Select):
        raise SQLValidationError("Only SELECT statements are allowed")

    for node in stmt.walk():
        if isinstance(node, FORBIDDEN_EXPRESSIONS):
            raise SQLValidationError(
                f"Forbidden statement type: {type(node).__name__}"
            )
        if isinstance(node, exp.Anonymous):
            # Unparsed function call — e.g. pg_sleep(10): name lives in .this
            fn = str(node.this).split("(")[0].strip('"').lower()
            if fn in DANGEROUS_FUNCTIONS:
                raise SQLValidationError(f"Forbidden function: {fn}")
        elif isinstance(node, exp.Func):
            fn = node.sql_name().lower()
            if fn in DANGEROUS_FUNCTIONS:
                raise SQLValidationError(f"Forbidden function: {fn}")

    # Tables: every table reference must be one of the allowed physical names.
    used_tables = {t.name.lower() for t in stmt.find_all(exp.Table)}
    if not used_tables or not used_tables <= {t.lower() for t in allowed_tables}:
        raise SQLValidationError(
            f"Query references tables outside the allowed dataset: {sorted(used_tables)}"
        )

    # Columns: names must exist in the allowed set (CTE aliases exempt —
    # they aren't exp.Column with a table ref).
    for col in stmt.find_all(exp.Column):
        if col.table and col.table.lower() not in {t.lower() for t in allowed_tables}:
            raise SQLValidationError(f"Column references disallowed table '{col.table}'")
        if col.name.lower() not in {c.lower() for c in allowed_columns} and col.name not in (
            "value", "t", "label"
        ):
            raise SQLValidationError(f"Unknown column '{col.name}'")

    # Enforce LIMIT.
    limit_expr = stmt.args.get("limit")
    if limit_expr is None:
        stmt = stmt.limit(row_cap)
    else:
        existing = int(limit_expr.expression.name)
        if existing > row_cap:
            stmt = stmt.limit(row_cap)

    return stmt.sql(dialect=dialect)


def dialect_for(engine_name: str) -> str:
    return {"postgresql": "postgres", "sqlite": "sqlite"}.get(engine_name, "postgres")
