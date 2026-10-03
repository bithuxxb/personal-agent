import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    api_key: str
    base_url: str | None
    model: str
    max_steps: int
    log_level: str
    workspace_dir: str


def load_settings() -> Settings:
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY 未设置，请复制 .env.example 为 .env 并填写")
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL") or None,
        model=os.environ.get("MODEL", "deepseek-chat"),
        max_steps=int(os.environ.get("MAX_STEPS", "8")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        workspace_dir=os.path.expanduser(
            os.environ.get("WORKSPACE_DIR", "~/Documents/AgentWorkspace")
        ),
    )
