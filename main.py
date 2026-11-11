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

# Our own additions on top of ADK's app
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))