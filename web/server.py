from collections import deque
from pathlib import Path

from agents import SQLiteSession
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import build_agent
from config import load_settings
from trace import run_agent

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Personal Agent")

settings = load_settings()
agent = build_agent(settings)
session = SQLiteSession("web", db_path="sessions.db")

traces: deque[dict] = deque(maxlen=50)


class ChatRequest(BaseModel):
    message: str


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC_DIR / "favicon.ico")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat")
async def chat(req: ChatRequest):
    events: list[dict] = []
    try:
        answer = await run_agent(
            agent,
            req.message,
            session=session,
            max_turns=settings.max_steps,
            on_event=events.append,
        )
    except Exception as exc:
        answer = f"出错: {exc}"
        if not any(e["type"] == "error" for e in events):
            events.append({
                "type": "error",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            })
    req_event = next((e for e in events if e["type"] == "request"), {})
    trace = {
        "request_id": req_event.get("request_id"),
        "timestamp": req_event.get("timestamp"),
        "model": req_event.get("model"),
        "user_input": req.message,
        "answer": answer,
        "events": events,
    }
    traces.appendleft(trace)
    return {"answer": answer, "trace": trace}


@app.get("/api/traces")
def list_traces():
    return {"traces": list(traces)}
