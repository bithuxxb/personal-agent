"""把 SDK 的 stream 事件映射成 PRD §15 的 trace 事件流，CLI 和 Web 共用。

事件类型：request / llm / tool_call / tool_result / final / stop / error，
字段与 v0.1 手搓 runtime 保持一致，前端 Trace 面板无需改动。
"""

import json
import time
import uuid
from datetime import datetime

from agents import MaxTurnsExceeded, Runner


def _usage_dict(u) -> dict | None:
    """Responses usage(input/output/total) 映射为 trace 沿用的 prompt/completion/total。"""
    if u is None:
        return None
    return {
        "prompt_tokens": getattr(u, "input_tokens", 0) or 0,
        "completion_tokens": getattr(u, "output_tokens", 0) or 0,
        "total_tokens": getattr(u, "total_tokens", 0) or 0,
    }


async def run_agent(agent, user_input: str, session, max_turns: int, on_event) -> str:
    request_id = uuid.uuid4().hex[:8]

    def emit(**event):
        event.setdefault("request_id", request_id)
        on_event(event)

    model_name = (
        agent.model
        if isinstance(agent.model, str)
        else getattr(agent.model, "model", type(agent.model).__name__)
    )
    emit(
        type="request",
        timestamp=datetime.now().isoformat(timespec="seconds"),
        user_input=user_input,
        model=model_name,
    )

    step = 0
    tools_used: list[str] = []
    token_usage = None
    last_mark = time.monotonic()
    current_tool = None
    answer = ""

    def acc_usage(usage):
        nonlocal token_usage
        if usage:
            if token_usage is None:
                token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            for key in token_usage:
                token_usage[key] += usage.get(key, 0)

    try:
        result = Runner.run_streamed(
            agent, user_input, session=session, max_turns=max_turns
        )
        async for event in result.stream_events():
            if (
                event.type == "raw_response_event"
                and event.data.type == "response.completed"
            ):
                step += 1
                now = time.monotonic()
                latency = round(now - last_mark, 3)
                last_mark = now
                resp = event.data.response
                usage = _usage_dict(getattr(resp, "usage", None))
                acc_usage(usage)
                has_tool = any(
                    getattr(o, "type", "") == "function_call"
                    for o in getattr(resp, "output", [])
                )
                emit(
                    type="llm",
                    step=step,
                    model=model_name,
                    latency=latency,
                    tool_call=has_tool,
                    usage=usage,
                )
            elif event.type == "run_item_stream_event":
                item = event.item
                if item.type == "tool_call_item":
                    current_tool = item.raw_item.name
                    emit(
                        type="tool_call",
                        step=step,
                        tool=current_tool,
                        arguments=getattr(item.raw_item, "arguments", ""),
                    )
                elif item.type == "tool_call_output_item":
                    out = item.output
                    payload = (
                        out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
                    )
                    success = True
                    try:
                        success = bool(json.loads(payload).get("success", True))
                    except (ValueError, AttributeError):
                        pass
                    tools_used.append(current_tool or "?")
                    emit(
                        type="tool_result",
                        step=step,
                        tool=current_tool,
                        success=success,
                        result=payload[:2000],
                    )
        answer = result.final_output or ""
        emit(type="final", step=step, answer=answer, token_usage=token_usage)
        return answer
    except MaxTurnsExceeded:
        summary = "、".join(
            f"{n}×{tools_used.count(n)}" for n in dict.fromkeys(tools_used)
        ) or "无"
        answer = (
            f"已达到最大执行步数（{max_turns}），任务未完成。"
            f"已执行的工具调用：{summary}。"
        )
        emit(
            type="stop", reason="max_steps", max_steps=max_turns, tools_used=tools_used
        )
        return answer
    except Exception as exc:
        emit(
            type="error",
            step=step or None,
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        raise
