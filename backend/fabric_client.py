"""Production data backend (stub) — a Microsoft Fabric SQL endpoint, reached
via pyodbc using an Azure AD service-principal token (azure-identity).

Not needed for the demo (DATA_SOURCE=demo uses sqlite_source.py instead), so
the pyodbc / azure-identity imports are lazy: this module can be imported
without either package installed as long as run_query()/get_schema() are
never actually called.

Implements the same run_query(sql) / get_schema() interface as
sqlite_source.py so data_source.py can dispatch to either one interchangeably.
"""
from backend import config
from backend.sql_guardrails import enforce_row_cap, validate_sql

_ODBC_DRIVER = "{ODBC Driver 18 for SQL Server}"
_FABRIC_SCOPE = "https://database.windows.net/.default"


def _get_connection():
    try:
        import pyodbc
        from azure.identity import ClientSecretCredential
    except ImportError as exc:
        raise RuntimeError(
            "pyodbc and azure-identity are required for DATA_SOURCE=fabric. "
            "Install them with `pip install pyodbc azure-identity` and configure "
            "an ODBC driver for SQL Server."
        ) from exc

    missing = [
        name
        for name, value in [
            ("FABRIC_SQL_SERVER", config.FABRIC_SQL_SERVER),
            ("FABRIC_SQL_DATABASE", config.FABRIC_SQL_DATABASE),
            ("AZURE_TENANT_ID", config.AZURE_TENANT_ID),
            ("AZURE_CLIENT_ID", config.AZURE_CLIENT_ID),
            ("AZURE_CLIENT_SECRET", config.AZURE_CLIENT_SECRET),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"DATA_SOURCE=fabric requires these env vars to be set: {', '.join(missing)}"
        )

    credential = ClientSecretCredential(
        tenant_id=config.AZURE_TENANT_ID,
        client_id=config.AZURE_CLIENT_ID,
        client_secret=config.AZURE_CLIENT_SECRET,
    )
    token = credential.get_token(_FABRIC_SCOPE).token

    # pyodbc expects the AAD access token packed as a raw byte struct.
    token_bytes = bytes(token, "utf-8")
    exptoken = b""
    for b in token_bytes:
        exptoken += bytes([b])
        exptoken += b"\x00"
    token_struct = len(exptoken).to_bytes(4, "little") + exptoken
    sql_copt_ss_access_token = 1256

    conn_str = (
        f"DRIVER={_ODBC_DRIVER};SERVER={config.FABRIC_SQL_SERVER};"
        f"DATABASE={config.FABRIC_SQL_DATABASE};Encrypt=yes;TrustServerCertificate=no;"
    )
    return pyodbc.connect(
        conn_str,
        attrs_before={sql_copt_ss_access_token: token_struct},
        timeout=config.QUERY_TIMEOUT_SECONDS,
    )


def get_schema() -> dict:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
        )
        tables: dict = {}
        for table_name, column_name, data_type in cur.fetchall():
            tables.setdefault(table_name, {"description": "", "columns": []})
            tables[table_name]["columns"].append({"name": column_name, "type": data_type, "primary_key": False})
        return {"dialect": "tsql", "tables": tables}
    finally:
        conn.close()


def run_query(sql: str) -> dict:
    clean_sql = validate_sql(sql)
    capped_sql = enforce_row_cap(clean_sql, config.MAX_ROWS)

    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(capped_sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(config.MAX_ROWS + 1)
        truncated = len(rows) > config.MAX_ROWS
        rows = rows[: config.MAX_ROWS]
        return {
            "columns": columns,
            "rows": [dict(zip(columns, r)) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "sql_executed": capped_sql,
        }
    finally:
        conn.close()
