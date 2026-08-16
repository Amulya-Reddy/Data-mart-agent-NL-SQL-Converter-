"""Demo data backend — a local SQLite file seeded by demo_data/seed_demo_data.py.
Implements the same run_query(sql) / get_schema() interface as fabric_client.py
so data_source.py can dispatch to either one interchangeably.
"""
import sqlite3
import time

from backend import config
from backend.sql_guardrails import enforce_row_cap, validate_sql

_TABLES = [
    "dim_Facility", "dim_Provider", "dim_Payer", "dim_Patient",
    "fact_Schedule", "fact_Surgery", "fact_Billing", "fact_Claims",
]

_TABLE_DESCRIPTIONS = {
    "dim_Facility": "One row per facility (hospital / surgical center).",
    "dim_Provider": "Surgeons, anesthesiologists, and CRNAs across all facilities.",
    "dim_Payer": "Insurance payers (commercial, Medicare, Medicaid, self-pay).",
    "dim_Patient": "Patient roster. Contains directly identifying fields (name, DOB, MRN) — prefer PatientID and aggregates unless the question specifically needs identity.",
    "fact_Schedule": "Scheduled OR cases, including cancellations and no-shows.",
    "fact_Surgery": "The case/incident anchor table — one row per completed surgical case with anesthesia timing.",
    "fact_Billing": "Charge/Payment/Adjustment transaction lines per case.",
    "fact_Claims": "Insurance claims per case: status, billed/allowed/paid amounts, denial reasons.",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DEMO_DB_PATH, timeout=config.QUERY_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema() -> dict:
    conn = _connect()
    try:
        cur = conn.cursor()
        tables = {}
        for table in _TABLES:
            cur.execute(f"PRAGMA table_info({table})")
            columns = [
                {"name": row["name"], "type": row["type"], "primary_key": bool(row["pk"])}
                for row in cur.fetchall()
            ]
            tables[table] = {
                "description": _TABLE_DESCRIPTIONS.get(table, ""),
                "columns": columns,
            }
        return {"dialect": "sqlite", "tables": tables}
    finally:
        conn.close()


def run_query(sql: str) -> dict:
    clean_sql = validate_sql(sql)
    capped_sql = enforce_row_cap(clean_sql, config.MAX_ROWS)

    conn = _connect()
    start = time.monotonic()
    try:
        cur = conn.cursor()
        cur.execute(capped_sql)
        rows = cur.fetchmany(config.MAX_ROWS + 1)
        elapsed = time.monotonic() - start
        if elapsed > config.QUERY_TIMEOUT_SECONDS:
            raise TimeoutError(f"Query exceeded {config.QUERY_TIMEOUT_SECONDS}s timeout.")

        truncated = len(rows) > config.MAX_ROWS
        rows = rows[: config.MAX_ROWS]
        columns = [d[0] for d in cur.description] if cur.description else []
        return {
            "columns": columns,
            "rows": [dict(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "sql_executed": capped_sql,
        }
    finally:
        conn.close()
