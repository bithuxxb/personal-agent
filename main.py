import asyncio

from agents import SQLiteSession

from agent import build_agent
from config import load_settings
from trace import run_agent

SESSION_DB = "sessions.db"


def cli_trace(event: dict) -> None:
    if event["type"] == "request":
        print(f"[request #{event['request_id']}] {event['timestamp']} · model={event.get('model')}")
    elif event["type"] == "llm":
        usage = event.get("usage") or {}
        tokens = usage.get("total_tokens", "?")
        mark = " → tool_call" if event["tool_call"] else ""
        print(f"[step {event['step']}] llm · {event['latency']}s · {tokens} tokens{mark}")
    elif event["type"] == "tool_call":
        args = str(event["arguments"])[:200]
        print(f"[tool] {event['tool']}({args})")
    elif event["type"] == "tool_result":
        print(f"[tool] result: {event['result'][:200]}")
    elif event["type"] == "stop":
        print(f"[stop] 达到最大步数 {event['max_steps']}")
    elif event["type"] == "error":
        print(f"[error] step {event.get('step')}: {event['error']['type']}: {event['error']['message']}")


async def main():
    settings = load_settings()
    agent = build_agent(settings)
    session = SQLiteSession("cli", db_path=SESSION_DB)

    print("Personal Agent · SDK 版（输入 exit 退出）\n")
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
            answer = await run_agent(
                agent,
                user_input,
                session=session,
                max_turns=settings.max_steps,
                on_event=cli_trace,
            )
        except Exception as exc:
            print(f"[error] {exc}\n")
            continue
        print(f"\nAssistant: {answer}\n")


if __name__ == "__main__":
    asyncio.run(main())
