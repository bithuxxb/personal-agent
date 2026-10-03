class AgentRuntime:
    """PRD §7。M1：纯对话循环；tool calling 与 MAX_STEPS 在 M2–M4 加入。"""

    def __init__(self, llm, system_prompt: str):
        self.llm = llm
        self.messages = [{"role": "system", "content": system_prompt}]

    def ask(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        answer = self.llm.generate(self.messages)
        self.messages.append({"role": "assistant", "content": answer})
        return answer
