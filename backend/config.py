"""Central config loaded from environment / .env. Nothing here talks to a
data backend directly — data_source.py reads these values to decide which
backend module to dispatch to."""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

DATA_SOURCE = os.getenv("DATA_SOURCE", "demo").strip().lower()

MAX_ROWS = _int("SQL_MAX_ROWS", 200)
QUERY_TIMEOUT_SECONDS = _int("SQL_QUERY_TIMEOUT_SECONDS", 10)
MAX_AGENT_TURNS = _int("AGENT_MAX_TURNS", 6)

DEMO_DB_PATH = os.getenv("DEMO_DB_PATH") or os.path.join(
    os.path.dirname(__file__), "..", "demo_data", "ncap_demo.db"
)

# Fabric / Azure — only read when DATA_SOURCE=fabric. Left unset in the demo.
FABRIC_SQL_SERVER = os.getenv("FABRIC_SQL_SERVER", "")
FABRIC_SQL_DATABASE = os.getenv("FABRIC_SQL_DATABASE", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*")
