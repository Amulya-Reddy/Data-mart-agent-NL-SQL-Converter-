"""Claude tool-use agent loop for the NCAP data mart. Two tools — get_schema
and run_sql — let Claude explore the active data source and answer in plain
language. Every run_sql call is recorded so the API can return a full query
trace back to the caller for transparency/audit.
"""
import json

import anthropic

from backend import config, data_source
from backend.sql_guardrails import SQLGuardrailError

SYSTEM_PROMPT = """You are the NCAP Data Mart Assistant, a natural-language query agent for an \
anesthesia billing/reconciliation data mart. Users ask questions in plain English; you answer \
using only data you retrieve via the run_sql tool.

Rules:
- Always call get_schema first if you haven't already seen the schema this conversation.
- Only query with SELECT/WITH statements — the run_sql tool enforces this, but never attempt \
  INSERT/UPDATE/DELETE/DDL.
- This is healthcare billing data. dim_Patient contains directly identifying fields (name, DOB, \
  MRN). Do not select those fields unless the user's question specifically requires patient \
  identity — prefer PatientID and aggregates for anything about volumes, trends, or billing.
- After you have enough information, give a clear, concise plain-language answer. Cite concrete \
  numbers from the query results.
- If a query returns no rows or an error, say so plainly rather than guessing.

Formatting:
- Do not use asterisks for bold/emphasis (no **text**). Write plain sentences instead.
- Use markdown tables for tabular data and plain paragraphs for takeaways — no bolded phrases \
  inside them.
- Keep the answer direct and numbers-first; skip filler like "Here's the breakdown:".
"""

TOOLS = [
    {
        "name": "get_schema",
        "description": (
            "Get the table and column metadata for the active data source, including which "
            "tables hold identifying patient fields."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_sql",
        "description": (
            "Run a single read-only SQL SELECT/WITH statement against the data mart and return "
            "the resulting rows and columns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT or WITH statement."}
            },
            "required": ["sql"],
        },
    },
]


def _execute_tool(name: str, tool_input: dict, query_log: list) -> tuple[str, bool]:
    """Returns (result_text, is_error)."""
    if name == "get_schema":
        try:
            schema = data_source.get_schema()
            return json.dumps(schema), False
        except Exception as exc:  # noqa: BLE001 - surface to the model as a tool error
            return f"Error fetching schema: {exc}", True

    if name == "run_sql":
        sql = tool_input.get("sql", "")
        try:
            result = data_source.run_query(sql)
            query_log.append(
                {
                    "sql": result["sql_executed"],
                    "row_count": result["row_count"],
                    "truncated": result["truncated"],
                    "mocked": False,
                }
            )
            return json.dumps({"columns": result["columns"], "rows": result["rows"]}), False
        except SQLGuardrailError as exc:
            query_log.append({"sql": sql, "row_count": 0, "truncated": False, "mocked": False})
            return f"Query rejected: {exc}", True
        except Exception as exc:  # noqa: BLE001
            query_log.append({"sql": sql, "row_count": 0, "truncated": False, "mocked": False})
            return f"Query failed: {exc}", True

    return f"Unknown tool: {name}", True


def ask(question: str) -> dict:
    """Runs the Claude agent loop for a single question. Returns
    {"answer": str, "queries": [...], "mocked": bool}."""
    if not config.ANTHROPIC_API_KEY:
        return {
            "answer": (
                "The backend has no ANTHROPIC_API_KEY configured, so this is a mocked response. "
                "Set ANTHROPIC_API_KEY in your .env to get real answers from Claude."
            ),
            "queries": [],
            "mocked": True,
        }

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": question}]
    query_log: list = []

    for _ in range(config.MAX_AGENT_TURNS):
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return {"answer": final_text or "(No answer text returned.)", "queries": query_log, "mocked": False}

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result_text, is_error = _execute_tool(block.name, block.input, query_log)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return {
        "answer": "Reached the maximum number of tool-use turns without a final answer. Try a more specific question.",
        "queries": query_log,
        "mocked": False,
    }
