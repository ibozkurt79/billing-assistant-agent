import os

import uvicorn
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ADK builds the FastAPI app: sessions, /run, /run_sse, list-apps.
# web=False -> no dev UI. Page and API share one origin, so no CORS list needed.
app = get_fast_api_app(
    agents_dir=BASE_DIR,
    web=False,
)

# Our own additions on top of ADK's app
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))