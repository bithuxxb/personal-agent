"""PRD §21 可自动化部分的验收脚本（契约测试，使用 mock LLM，不依赖真实模型）。

运行：.venv/bin/python tests/acceptance.py
"""

import itertools
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.loop import AgentRuntime
from tools import local_file, web
from tools.base import Tool, ToolResult
from tools.registry import ToolRegistry

PASSED = []
FAILED = []


def check(name: str, cond: bool, detail: str = ""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")


class FakeCall:
    def __init__(self, name: str, arguments: str):
        self.id = "call_1"
        self.function = type("F", (), {"name": name, "arguments": arguments})()


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in self.tool_calls
            ]
        return {k: v for k, v in d.items() if v is not None} if exclude_none else d


class ScriptLLM:
    """按预设脚本依次返回响应。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def generate(self, messages, tools=None):
        self.calls += 1
        return self.script.pop(0), None


class LoopLLM:
    """永远返回 tool_call，用于触发 MAX_STEPS。"""

    def __init__(self):
        self.calls = 0

    def generate(self, messages, tools=None):
        self.calls += 1
        return FakeMessage(tool_calls=[FakeCall("calculator", '{"expression": "1+1"}')]), None


def make_agent(llm, extra_tools=(), max_steps=8, workspace=None):
    registry = ToolRegistry()
    for t in extra_tools:
        registry.register(t)
    if workspace:
        registry.register(local_file.make_tool(workspace))
    events = []
    agent = AgentRuntime(llm, registry, "测试", max_steps=max_steps, on_event=events.append)
    return agent, events


ws = tempfile.mkdtemp(prefix="agent-test-")
Path(ws, "test.md").write_text("# 测试\n内容", encoding="utf-8")

# --- Test 3: read_file 正常读取 ---
agent, events = make_agent(
    ScriptLLM([
        FakeMessage(tool_calls=[FakeCall("read_file", '{"path": "test.md"}')]),
        FakeMessage(content="已读取"),
    ]),
    workspace=ws,
)
answer = agent.ask("读取 test.md")
tool_msg = next(m for m in agent.messages if m.get("role") == "tool")
check("Test 3 read_file 正常读取", '"success": true' in tool_msg["content"] and answer == "已读取")

# --- Test 4: ~/.ssh 拒绝，且内容不进入 context ---
agent, events = make_agent(
    ScriptLLM([
        FakeMessage(tool_calls=[FakeCall("read_file", '{"path": "~/.ssh/id_rsa"}')]),
        FakeMessage(content="无权访问该文件"),
    ]),
    workspace=ws,
)
answer = agent.ask("读取 ~/.ssh/id_rsa")
tool_msg = next(m for m in agent.messages if m.get("role") == "tool")
check(
    "Test 4 ~/.ssh 被拒绝",
    "permission_denied" in tool_msg["content"] and answer == "无权访问该文件",
)

# --- 路径逃逸组：symlink / .. / 同名前缀目录 ---
rf = local_file.make_tool(ws)
outside = Path(ws).parent / f"{Path(ws).name}-backup"
outside.mkdir(exist_ok=True)
(outside / "secret.txt").write_text("secret")
Path(ws, "evil-link").unlink(missing_ok=True)
Path(ws, "evil-link").symlink_to(Path.home() / ".ssh")
check("逃逸: 符号链接", not rf.execute({"path": "evil-link"}).success)
check("逃逸: .. 穿越", not rf.execute({"path": "../../.." + str(outside / "secret.txt")}).success)
check("逃逸: 同名前缀目录", not rf.execute({"path": str(outside / "secret.txt")}).success)
check("逃逸后白名单内仍正常", rf.execute({"path": "test.md"}).success)

# --- Test 5: 工具失败不崩溃，错误回传给模型 ---
failing = Tool(
    name="always_fails",
    description="总是失败",
    parameters={"type": "object", "properties": {}},
    func=lambda: ToolResult(success=False, error={"type": "boom", "message": "模拟失败"}),
)
agent, events = make_agent(
    ScriptLLM([
        FakeMessage(tool_calls=[FakeCall("always_fails", "{}")]),
        FakeMessage(content="工具失败了，换一种方式"),
    ]),
    extra_tools=[failing],
)
answer = agent.ask("触发失败")
check("Test 5 工具失败不崩溃", answer == "工具失败了，换一种方式")
check("Test 5 错误结构化回传", any(
    e["type"] == "tool_result" and not e["success"] and "boom" in e["result"] for e in events
))

# --- Test 7: 无限调用被 MAX_STEPS 终止 ---
llm = LoopLLM()
agent, events = make_agent(llm, extra_tools=[__import__("tools.calculator", fromlist=["tool"]).tool], max_steps=3)
answer = agent.ask("诱导无限循环")
check(
    "Test 7 MAX_STEPS 终止",
    llm.calls == 3 and "已达到最大执行步数（3）" in answer,
    f"calls={llm.calls}",
)
check("Test 7 stop 事件 + 工具摘要", any(
    e["type"] == "stop" and e["tools_used"] == ["calculator"] * 3 for e in events
))

# --- 协议边角: 未知工具 / 非法 JSON ---
agent, events = make_agent(
    ScriptLLM([
        FakeMessage(tool_calls=[FakeCall("nonexistent", "{}")]),
        FakeMessage(content="好"),
    ])
)
agent.ask("x")
tool_msg = next(m for m in agent.messages if m.get("role") == "tool")
check("未知工具返回结构化错误", "unknown_tool" in tool_msg["content"])

agent, events = make_agent(
    ScriptLLM([
        FakeMessage(tool_calls=[FakeCall("calculator", "{bad json")]),
        FakeMessage(content="好"),
    ]),
    extra_tools=[__import__("tools.calculator", fromlist=["tool"]).tool],
)
agent.ask("x")
tool_msg = next(m for m in agent.messages if m.get("role") == "tool")
check("非法 JSON 参数不崩溃", "invalid_json" in tool_msg["content"])

# --- 权限级: Level 2 工具被拒绝 ---
lv2 = Tool(
    name="save_note",
    description="写操作",
    parameters={"type": "object", "properties": {}},
    func=lambda: ToolResult(success=True, data={}),
    permission_level=2,
)
agent, _ = make_agent(
    ScriptLLM([
        FakeMessage(tool_calls=[FakeCall("save_note", "{}")]),
        FakeMessage(content="好"),
    ]),
    extra_tools=[lv2],
)
agent.ask("x")
tool_msg = next(m for m in agent.messages if m.get("role") == "tool")
check("Level 2 工具默认拒绝", "permission_denied" in tool_msg["content"])

# --- Context 截断: 不切断 tool_call/tool_result 组 ---
from runtime.loop import MAX_CONTEXT_MESSAGES

agent, events = make_agent(ScriptLLM([FakeMessage(content="ok")]))
agent.messages = [{"role": "system", "content": "s"}]
for i in range(MAX_CONTEXT_MESSAGES):
    agent.messages.append({"role": "user", "content": f"q{i}"})
    agent.messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": "c"}]})
    agent.messages.append({"role": "tool", "tool_call_id": "c", "content": "r"})
agent._trim_context()
check("截断后保留 system", agent.messages[0]["role"] == "system")
check("截断后不出现孤儿 tool 消息", agent.messages[1]["role"] != "tool")
check("截断后长度受控", len(agent.messages) <= MAX_CONTEXT_MESSAGES + 1)

# --- web_fetch SSRF 静态校验（不发请求的分支）---
check("SSRF: file:// 拒绝", not web.web_fetch.execute({"url": "file:///etc/passwd"}).success)
check("SSRF: 内网 IP 拒绝", not web.web_fetch.execute({"url": "http://192.168.1.1/"}).success)
check("SSRF: metadata 地址拒绝", not web.web_fetch.execute({"url": "http://169.254.169.254/"}).success)

# --- Trace 字段完整性（PRD §15）---
agent, events = make_agent(
    ScriptLLM([
        FakeMessage(tool_calls=[FakeCall("read_file", '{"path": "test.md"}')]),
        FakeMessage(content="总结完毕"),
    ]),
    workspace=ws,
)
agent.ask("读一下 test.md")
req_ev = next(e for e in events if e["type"] == "request")
check(
    "Trace: request 含 request_id/timestamp/user_input/model",
    all(k in req_ev for k in ("request_id", "timestamp", "user_input", "model"))
    and req_ev["user_input"] == "读一下 test.md",
)
llm_evs = [e for e in events if e["type"] == "llm"]
check(
    "Trace: llm 事件含 step/model/latency/usage",
    len(llm_evs) == 2
    and all(all(k in e for k in ("step", "model", "latency", "usage")) for e in llm_evs),
)
check(
    "Trace: 所有事件带同一 request_id",
    all(e.get("request_id") == req_ev["request_id"] for e in events),
)
tool_ev = next(e for e in events if e["type"] == "tool_call")
check(
    "Trace: tool_call 含 step/tool_name/arguments",
    all(k in tool_ev for k in ("step", "tool", "arguments")),
)
final_ev = next(e for e in events if e["type"] == "final")
check(
    "Trace: final 含 answer 和累计 token_usage",
    final_ev["answer"] == "总结完毕" and "token_usage" in final_ev,
)

# --- LLM 错误结构化入 Trace（§15 error 字段）---
class FailLLM:
    model = "fail-model"

    def generate(self, messages, tools=None):
        raise RuntimeError("api 炸了")

agent, events = make_agent(FailLLM())
try:
    agent.ask("x")
    raised = False
except RuntimeError:
    raised = True
err_ev = next((e for e in events if e["type"] == "error"), None)
check(
    "Trace: LLM 异常产生 error 事件后继续上抛",
    raised
    and err_ev is not None
    and err_ev["error"]["type"] == "RuntimeError"
    and err_ev["step"] == 1
    and err_ev.get("request_id"),
)

# --- LLM 重试可观察（§16 重试过程入 Trace）---
from unittest.mock import patch

import httpx
from openai import RateLimitError

from llm.client import LLMClient

client = LLMClient(api_key="k", model="m")
retries = []
client.on_retry = lambda attempt, exc: retries.append((attempt, type(exc).__name__))
rl_err = RateLimitError(
    "rate limited",
    response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
    body=None,
)


class FlakyCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= 2:
            raise rl_err
        return type(
            "Resp",
            (),
            {
                "usage": None,
                "choices": [type("C", (), {"message": FakeMessage(content="ok")})()],
            },
        )()


client._client = type(
    "C", (), {"chat": type("Ch", (), {"completions": FlakyCompletions()})()}
)()
with patch("llm.client.time.sleep"):
    msg, _ = client.generate([{"role": "user", "content": "x"}])
check(
    "LLM 重试两次后成功且回调可观察",
    msg.content == "ok" and retries == [(1, "RateLimitError"), (2, "RateLimitError")],
    f"retries={retries}",
)

# Runtime 自动接管 LLMClient 的 on_retry，汇入统一事件流
client2 = LLMClient(api_key="k", model="m")
agent, events = make_agent(client2)
check("Runtime 接管 llm.on_retry", client2.on_retry is not None)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
