from config import load_settings
from llm.client import LLMClient
from runtime.loop import AgentRuntime
from tools import calculator
from tools.registry import ToolRegistry

SYSTEM_PROMPT = "你是一个个人技术助手，回答简洁准确。需要计算时使用 calculator 工具。"


def main():
    settings = load_settings()
    llm = LLMClient(
        api_key=settings.api_key,
        model=settings.model,
        base_url=settings.base_url,
    )
    registry = ToolRegistry()
    registry.register(calculator.tool)
    agent = AgentRuntime(
        llm, registry, system_prompt=SYSTEM_PROMPT, max_steps=settings.max_steps
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
