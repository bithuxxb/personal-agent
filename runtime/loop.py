import json
import time
import uuid
from datetime import datetime

from tools.base import ToolResult

MAX_CONTEXT_MESSAGES = 40


class AgentRuntime:
    """PRD §7。tool calling 循环 + MAX_STEPS + context 截断；
    trace 以结构化事件发出，CLI/Web 各自订阅。
    事件字段覆盖 PRD §15：request_id / timestamp / user_input / model /
    step / tool_name / tool_arguments / tool_result / latency / token_usage /
    error / final_response。"""

    def __init__(self, llm, registry, system_prompt: str, max_steps: int = 8, on_event=None):
        self.llm = llm
        self.registry = registry
        self.max_steps = max_steps
        self.on_event = on_event or (lambda event: None)
        self._system_prompt = system_prompt
        self.messages = [{"role": "system", "content": system_prompt}]
        self._request_id: str | None = None
        # LLM 重试也纳入 trace（§16 的重试过程可观察）
        if hasattr(llm, "on_retry"):
            llm.on_retry = self._on_llm_retry

    def _emit(self, **event):
        event.setdefault("request_id", self._request_id)
        self.on_event(event)

    def _on_llm_retry(self, attempt: int, exc: Exception):
        self._emit(
            type="llm_retry",
            attempt=attempt,
            error={"type": type(exc).__name__, "message": str(exc)},
        )

    def _refresh_datetime(self):
        """每次请求把真实当前日期时间写进 system prompt。
        模型知识有截止日期，"今天/最近"类请求不能靠它自己推算。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
        self.messages[0] = {
            "role": "system",
            "content": (
                f"{self._system_prompt}\n\n"
                f"当前日期时间：{now}。"
                f"涉及“今天”“最近”“最新”等时效性请求时，以此日期为准生成搜索关键词。"
            ),
        }

    def _trim_context(self):
        """PRD §13：简单截断。硬性规则——不得把 tool_call 和它的 tool_result 切断，
        所以截断以消息组为单位：删除最旧一条后，若下一条是孤儿 tool 消息则一并删除。"""
        while len(self.messages) > MAX_CONTEXT_MESSAGES + 1:
            del self.messages[1]
            while len(self.messages) > 1 and self.messages[1].get("role") == "tool":
                del self.messages[1]
            self._emit(type="context_trim", remaining=len(self.messages))

    def ask(self, user_input: str) -> str:
        self._request_id = uuid.uuid4().hex[:8]
        self._refresh_datetime()
        self._emit(
            type="request",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            user_input=user_input,
            model=getattr(self.llm, "model", None),
        )
        self.messages.append({"role": "user", "content": user_input})
        tools_used: list[str] = []
        # 至少收到过一次 usage 才累计；全程缺失则保持 None（未知），不记为零
        token_usage = None
        step = 0
        while step < self.max_steps:
            step += 1
            self._trim_context()
            start = time.monotonic()
            try:
                msg, usage = self.llm.generate(
                    self.messages, tools=self.registry.schemas() or None
                )
            except Exception as exc:
                self._emit(
                    type="error",
                    step=step,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
                raise
            latency = round(time.monotonic() - start, 3)
            if usage:
                if token_usage is None:
                    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                for key in token_usage:
                    token_usage[key] += usage.get(key, 0)
            tool_calls = getattr(msg, "tool_calls", None)
            self._emit(
                type="llm",
                step=step,
                model=getattr(self.llm, "model", None),
                latency=latency,
                tool_call=bool(tool_calls),
                usage=usage,
            )
            if not tool_calls:
                answer = msg.content or ""
                self.messages.append({"role": "assistant", "content": answer})
                self._emit(type="final", step=step, answer=answer, token_usage=token_usage)
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
                tools_used.append(name)
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

        summary = "、".join(
            f"{n}×{tools_used.count(n)}" for n in dict.fromkeys(tools_used)
        ) or "无"
        fallback = (
            f"已达到最大执行步数（{self.max_steps}），任务未完成。"
            f"已执行的工具调用：{summary}。"
        )
        self._emit(
            type="stop", reason="max_steps", max_steps=self.max_steps, tools_used=tools_used
        )
        return fallback
