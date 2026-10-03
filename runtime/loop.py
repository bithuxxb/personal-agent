import json
import time

from tools.base import ToolResult


class AgentRuntime:
    """PRD §7。M2/M3：tool calling 循环；trace 以结构化事件发出，CLI/Web 各自订阅。"""

    def __init__(self, llm, registry, system_prompt: str, max_steps: int = 8, on_event=None):
        self.llm = llm
        self.registry = registry
        self.max_steps = max_steps
        self.on_event = on_event or (lambda event: None)
        self.messages = [{"role": "system", "content": system_prompt}]

    def _emit(self, **event):
        self.on_event(event)

    def ask(self, user_input: str) -> str:
        self._emit(type="request", user_input=user_input)
        self.messages.append({"role": "user", "content": user_input})
        step = 0
        while step < self.max_steps:
            step += 1
            start = time.monotonic()
            msg = self.llm.generate(
                self.messages, tools=self.registry.schemas() or None
            )
            latency = round(time.monotonic() - start, 3)
            tool_calls = getattr(msg, "tool_calls", None)
            self._emit(
                type="llm", step=step, latency=latency, tool_call=bool(tool_calls)
            )
            if not tool_calls:
                answer = msg.content or ""
                self.messages.append({"role": "assistant", "content": answer})
                self._emit(type="final", answer=answer)
                return answer

            self.messages.append(msg.model_dump(exclude_none=True))
            for call in tool_calls:
                name = call.function.name
                self._emit(
                    type="tool_call",
                    step=step,
                    tool=name,
                    arguments=call.function.arguments,
                )
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
                payload = json.dumps(result.to_dict(), ensure_ascii=False)
                self._emit(
                    type="tool_result",
                    step=step,
                    tool=name,
                    success=result.success,
                    result=payload[:2000],
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": payload,
                    }
                )

        fallback = f"已达到最大执行步数（{self.max_steps}），任务未完成。"
        self._emit(type="stop", reason="max_steps", max_steps=self.max_steps)
        return fallback
