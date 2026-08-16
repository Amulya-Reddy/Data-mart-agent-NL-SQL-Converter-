"""aiohttp entrypoint that exposes the Teams bot over the Bot Framework
messaging endpoint (POST /api/messages).

Run:
    python teams_bot/app.py

Configure via .env: MICROSOFT_APP_ID, MICROSOFT_APP_PASSWORD, NCAP_BACKEND_URL.

NOTE: This code only implements the bot logic and message adapter. Creating
the actual Azure Bot resource, registering the Teams channel, and uploading
the app manifest/package to Teams are manual steps in the Azure Portal and
Teams admin center — see README.md "Path to production".
"""
import os
import sys
import traceback
from datetime import datetime

from aiohttp import web
from aiohttp.web import Request, Response, json_response
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from teams_bot.bot import NcapDataMartBot  # noqa: E402

load_dotenv()

APP_ID = os.environ.get("MICROSOFT_APP_ID", "")
APP_PASSWORD = os.environ.get("MICROSOFT_APP_PASSWORD", "")

settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(settings)


async def on_error(context: TurnContext, error: Exception):
    print(f"[teams_bot error] {error}", file=sys.stderr)
    traceback.print_exc()
    await context.send_activity("The bot hit an unexpected error processing that request.")


adapter.on_turn_error = on_error

bot = NcapDataMartBot()


async def messages(req: Request) -> Response:
    if "application/json" not in req.headers.get("Content-Type", ""):
        return Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    response = await adapter.process_activity(activity, auth_header, bot.on_turn)
    if response:
        return json_response(data=response.body, status=response.status)
    return Response(status=201)


async def health(req: Request) -> Response:
    return json_response({"status": "ok", "time": datetime.utcnow().isoformat()})


app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_get("/health", health)

if __name__ == "__main__":
    port = int(os.environ.get("TEAMS_BOT_PORT", "3978"))
    web.run_app(app, host="0.0.0.0", port=port)
