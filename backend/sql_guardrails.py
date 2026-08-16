"""SQL safety checks shared by every data_source backend (sqlite_source.py,
fabric_client.py, and any future one). Keeping this in a single module means
the read-only/row-cap policy can't drift between backends.
"""
import re

from backend import config

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|MERGE|EXEC|EXECUTE|GRANT|REVOKE|CREATE|ATTACH|DETACH|PRAGMA|VACUUM|REPLACE)\b",
    re.IGNORECASE,
)

_LEADING_KEYWORD = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

_MULTIPLE_STATEMENTS = re.compile(r";\s*\S")


class SQLGuardrailError(ValueError):
    """Raised when a SQL statement fails a safety check."""


def validate_sql(sql: str) -> str:
    """Raises SQLGuardrailError if `sql` isn't a safe, single, read-only
    statement. Returns the trimmed SQL on success."""
    if not sql or not sql.strip():
        raise SQLGuardrailError("Empty SQL statement.")

    cleaned = sql.strip().rstrip(";").strip()

    if not _LEADING_KEYWORD.match(cleaned):
        raise SQLGuardrailError(
            "Only SELECT or WITH statements are allowed. This is a read-only data mart."
        )

    if _FORBIDDEN_KEYWORDS.search(cleaned):
        raise SQLGuardrailError(
            "Statement contains a forbidden keyword (data-modifying or DDL statements are blocked)."
        )

    if _MULTIPLE_STATEMENTS.search(sql.strip()):
        raise SQLGuardrailError("Multiple statements in one call are not allowed.")

    return cleaned


def enforce_row_cap(sql: str, max_rows: int = None) -> str:
    """Best-effort LIMIT injection for backends that don't already cap rows
    themselves. Only applied when the query has no existing LIMIT clause."""
    max_rows = max_rows or config.MAX_ROWS
    if re.search(r"\bLIMIT\s+\d+\s*$", sql, re.IGNORECASE):
        return sql
    return f"{sql}\nLIMIT {max_rows}"
