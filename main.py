from config import load_settings
from llm.client import LLMClient
from runtime.loop import AgentRuntime

SYSTEM_PROMPT = "你是一个个人技术助手，回答简洁准确。"


def main():
    settings = load_settings()
    llm = LLMClient(api_key=settings.openai_api_key, model=settings.model)
    agent = AgentRuntime(llm, system_prompt=SYSTEM_PROMPT)

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
