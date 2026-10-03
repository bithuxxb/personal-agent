import json

from tools.base import ToolResult


class AgentRuntime:
    """PRD §7。M2：tool calling 循环 + Trace 骨架；MAX_STEPS 与错误处理在 M4 完善。"""

    def __init__(self, llm, registry, system_prompt: str, max_steps: int = 8):
        self.llm = llm
        self.registry = registry
        self.max_steps = max_steps
        self.messages = [{"role": "system", "content": system_prompt}]

    def ask(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        step = 0
        while step < self.max_steps:
            step += 1
            msg = self.llm.generate(
                self.messages, tools=self.registry.schemas() or None
            )
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                answer = msg.content or ""
                self.messages.append({"role": "assistant", "content": answer})
                return answer

            print(f"[step {step}] llm → tool_call")
            self.messages.append(msg.model_dump(exclude_none=True))
            for call in tool_calls:
                name = call.function.name
                print(f"[tool] {name}({call.function.arguments})")
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    result = ToolResult(
                        success=False,
                        error={
                            "type": "invalid_json",
                            "message": f"模型返回了非法 JSON 参数: {exc}",
                        },
                    )
                else:
                    result = self.registry.execute(name, arguments)
                preview = json.dumps(result.to_dict(), ensure_ascii=False)[:200]
                print(f"[tool] result: {preview}")
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result.to_dict(), ensure_ascii=False),
                    }
                )

        fallback = f"已达到最大执行步数（{self.max_steps}），任务未完成。"
        print(f"[stop] {fallback}")
        return fallback
