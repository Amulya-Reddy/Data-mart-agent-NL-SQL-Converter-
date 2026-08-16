"""Bot Framework activity handler for the NCAP Data Mart Agent.

This is a thin wrapper only — all agent logic lives in the FastAPI backend
(backend/agent.py). Every incoming Teams message is forwarded to POST
/api/ask, and the reply is the same answer + SQL trace shown in the web UI.

NOTE: Registering a real Azure Bot resource (App ID / password, Teams channel
registration, the manifest package) is a manual step in the Azure Portal /
Teams admin center — outside the scope of this code. See README.md "Path to
production" for details.
"""
import os

import aiohttp
from botbuilder.core import ActivityHandler, TurnContext

BACKEND_URL = os.environ.get("NCAP_BACKEND_URL", "http://localhost:8000")


class NcapDataMartBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        question = (turn_context.activity.text or "").strip()
        if not question:
            await turn_context.send_activity("Ask me a question about the NCAP data mart.")
            return

        await turn_context.send_activity("Looking into that…")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BACKEND_URL}/api/ask",
                    json={"question": question},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            await turn_context.send_activity(f"Sorry, I couldn't reach the data mart backend: {exc}")
            return

        reply = data.get("answer", "(no answer returned)")
        if data.get("mocked"):
            reply += "\n\n_(mocked response — backend has no ANTHROPIC_API_KEY set)_"

        queries = data.get("queries") or []
        if queries:
            sql_block = "\n\n".join(
                f"-- {q['row_count']} row(s){' (truncated)' if q.get('truncated') else ''}\n{q['sql']}"
                for q in queries
            )
            reply += f"\n\n**SQL run:**\n```sql\n{sql_block}\n```"

        await turn_context.send_activity(reply)
