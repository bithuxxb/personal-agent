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


def cli_trace(event: dict) -> None:
    if event["type"] == "tool_call":
        args = event["arguments"][:200]
        print(f"[step {event['step']}] {event['tool']}({args})")
    elif event["type"] == "tool_result":
        print(f"[tool] result: {event['result'][:200]}")
    elif event["type"] == "stop":
        print(f"[stop] 达到最大步数 {event['max_steps']}")


def main():
    settings = load_settings()
    llm = LLMClient(
        api_key=settings.api_key,
        model=settings.model,
        base_url=settings.base_url,
    )
    registry = ToolRegistry()
    registry.register(calculator.tool)
    registry.register(web.web_search)
    registry.register(web.web_fetch)
    registry.register(local_file.make_tool(settings.workspace_dir))
    agent = AgentRuntime(
        llm,
        registry,
        system_prompt=SYSTEM_PROMPT,
        max_steps=settings.max_steps,
        on_event=cli_trace,
    )

    print("Personal Agent v0.1（输入 exit 退出）\n")
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break
        try:
            answer = agent.ask(user_input)
        except Exception as exc:
            print(f"[error] {exc}\n")
            continue
        print(f"\nAssistant: {answer}\n")


if __name__ == "__main__":
    main()
