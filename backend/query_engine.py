import os
import re
import sqlite3


DB_PATH = os.path.join(os.path.dirname(__file__), "o2c.db")


def validate_sql(sql: str) -> str:
    normalized = (sql or "").strip()
    if not normalized:
        raise ValueError("The generated query was empty.")

    if ";" in normalized.rstrip(";"):
        raise ValueError("Only a single query is allowed.")

    compact = normalized.upper().lstrip()
    if not (compact.startswith("SELECT") or compact.startswith("WITH")):
        raise ValueError("Only SELECT queries are allowed.")

    forbidden_tokens = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "REINDEX",
        "VACUUM",
    ]
    if any(re.search(rf"\b{token}\b", compact) for token in forbidden_tokens):
        raise ValueError("Only read-only analytical queries are allowed.")

    return normalized.rstrip(";")


def run_sql(sql: str) -> list[dict]:
    normalized_sql = validate_sql(sql)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(normalized_sql).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
