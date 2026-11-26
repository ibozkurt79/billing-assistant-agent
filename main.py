import asyncio
import json
import re

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import JSONResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

import os

import uvicorn
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app

import time
from opentelemetry import trace as otel_trace

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Local runs: load the agent's .env so GOOGLE_CLOUD_PROJECT exists before the agent loads.
# On Cloud Run the env vars come from --set-env-vars (.env isn't uploaded).
load_dotenv(os.path.join(BASE_DIR, "billing_assistant", ".env"))

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
_google_request = google_requests.Request()

PUBLIC_PATHS = {"/", "/favicon.ico"}
USER_PATH = re.compile(r"^/apps/[^/]+/users/([^/]+)")   # captures {userId} in ADK session URLs


def verify_token(token: str) -> dict:
    """Checks signature (Google public keys), iss, aud, exp. Raises if anything is wrong."""
    return id_token.verify_firebase_token(token, _google_request, audience=PROJECT_ID)
# ADK builds the FastAPI app: sessions, /run, /run_sse, list-apps.
# web=False -> no dev UI. Page and API share one origin, so no CORS list needed.

app = get_fast_api_app(
    agents_dir=BASE_DIR,
    web=False,
    trace_to_cloud=os.environ.get("TRACE_TO_CLOUD", "true") == "true",  # spans -> Cloud Trace
)

@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path

    # 1. Public: the page and its files (the login form must load before sign-in)
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    # 2. Everything else needs a Bearer token
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse({"detail": "login required"}, status_code=401)

    try:
        # verify_firebase_token does blocking HTTP (fetches Google's keys) -> run in a thread
        claims = await asyncio.to_thread(verify_token, auth.removeprefix("Bearer "))
    except Exception:
        return JSONResponse({"detail": "invalid or expired token"}, status_code=401)

    uid = claims["sub"]
    # Absolute session limit: force a fresh sign-in 8 h after the password was entered,
    # even if the browser keeps refreshing tokens
    if time.time() - claims.get("auth_time", 0) > 2 * 3600:
        return JSONResponse({"detail": "session expired, sign in again"}, status_code=401)
    # 3. Ownership: /apps/{app}/users/{userId}/... must be the caller's own uid
    m = USER_PATH.match(path)
    if m and m.group(1) != uid:
        return JSONResponse({"detail": "forbidden"}, status_code=403)

    # 4. Ownership for /run and /run_sse: userId is in the JSON body
    if path in ("/run", "/run_sse"):
        try:
            body = json.loads(await request.body() or b"{}")
        except json.JSONDecodeError:
            return JSONResponse({"detail": "bad request"}, status_code=400)
        if body.get("userId") != uid:
            return JSONResponse({"detail": "forbidden"}, status_code=403)

    return await call_next(request)

MAX_TEXT = 8000   # cap chat text per log line (a Cloud Logging entry is limited to 256 KB)
MAX_TOOL_RESULT = 6000   # cap each tool result (JSON text) in the log line

@app.middleware("http")
async def agent_turn_metrics(request: Request, call_next):
    """One structured log line per /run_sse turn: timings, error flag, tools used, question and final answer."""
    if request.url.path != "/run_sse":
        return await call_next(request)

    start = time.monotonic()
    span_ctx = otel_trace.get_current_span().get_span_context()
    trace_id = f"{span_ctx.trace_id:032x}" if span_ctx.is_valid else None

    try:
        req = json.loads(await request.body() or b"{}")
    except ValueError:
        req = {}
    new_message = req.get("newMessage") or req.get("new_message") or {}
    question = "".join(p.get("text", "") for p in new_message.get("parts", []))

    response = await call_next(request)
    body = response.body_iterator

    async def timed_body():
        first_text_ms, answer, tools, tool_results = None, "", [], []
        agent_error = response.status_code >= 400
        try:
            async for chunk in body:
                text = chunk.decode("utf-8", "ignore") if isinstance(chunk, bytes) else chunk
                for line in text.splitlines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:])
                    except ValueError:
                        continue
                    if "error" in event or "errorCode" in event:   # exception event, or model error event
                        agent_error = True
                    content = event.get("content") or {}
                    parts = content.get("parts", []) if content.get("role") == "model" else []
                    texts = [p["text"] for p in parts if p.get("text") and not p.get("thought")]
                    if texts and first_text_ms is None:
                        first_text_ms = round((time.monotonic() - start) * 1000)
                    if texts and not event.get("partial"):
                        answer = "".join(texts)          # last complete model message = the final answer
                    for p in parts:
                        name = (p.get("functionCall") or {}).get("name")
                        if name and name not in tools:
                            tools.append(name)
                    for p in content.get("parts") or []:           # tool results arrive as user-role events
                        fr = p.get("functionResponse")
                        if fr:
                            tool_results.append({
                                "name": fr.get("name"),
                                "response_json": json.dumps(fr.get("response"), default=str)[:MAX_TOOL_RESULT],
                            })
                yield chunk
        finally:
            entry = {
                "message": "agent_turn",
                "severity": "ERROR" if agent_error else "INFO",
                "ttft_ms": first_text_ms,
                "total_ms": round((time.monotonic() - start) * 1000),
                "agent_error": agent_error,
                "status": response.status_code,
                "session_id": req.get("sessionId"),
                "tools": tools,
                "tool_results": tool_results,
                "question": question[:MAX_TEXT],
                "answer": answer[:MAX_TEXT],
            }
            if trace_id:
                entry["logging.googleapis.com/trace"] = f"projects/{PROJECT_ID}/traces/{trace_id}"
            print(json.dumps(entry), flush=True)

    response.body_iterator = timed_body()
    return response

# Our own additions on top of ADK's app
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))