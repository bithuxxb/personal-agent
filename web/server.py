from collections import deque
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import load_settings
from llm.client import LLMClient
from runtime.loop import AgentRuntime
from tools import calculator, local_file, web
from tools.registry import ToolRegistry

SYSTEM_PROMPT = (
    "你是一个个人技术助手，回答简洁准确。"
    "需要计算时用 calculator；需要实时信息时用 web_search，"
    "需要读网页正文时用 web_fetch；需要读本地文件时用 read_file。"
)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Personal Agent v0.1")

settings = load_settings()
llm = LLMClient(
    api_key=settings.api_key, model=settings.model, base_url=settings.base_url
)
registry = ToolRegistry()
registry.register(calculator.tool)
registry.register(web.web_search)
registry.register(web.web_fetch)
registry.register(local_file.make_tool(settings.workspace_dir))
agent = AgentRuntime(
    llm, registry, system_prompt=SYSTEM_PROMPT, max_steps=settings.max_steps
)

traces: deque[dict] = deque(maxlen=50)


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat")
def chat(req: ChatRequest):
    events: list[dict] = []
    agent.on_event = events.append
    try:
        answer = agent.ask(req.message)
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
