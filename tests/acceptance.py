"""SDK 版验收脚本（PRD §21 可自动化部分）。

LLM 用 SDK 自带的 agents.testing.ScriptedModel 按脚本回放，
不依赖真实模型。运行：.venv/bin/python tests/acceptance.py
"""

import asyncio
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import Agent, SQLiteSession, Usage
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from agent import BASE_INSTRUCTIONS, _instructions, build_agent, calculator
from config import Settings
from tools.local_file import make_read_file
from tools.web import _TextExtractor, web_fetch
from trace import run_agent

PASSED = []
FAILED = []


def check(name: str, cond: bool, detail: str = ""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail if not cond else ''}")


def make_settings(workspace: str) -> Settings:
    return Settings(
        api_key="test-key",
        base_url=None,
        model="test-model",
        max_steps=8,
        log_level="INFO",
        workspace_dir=workspace,
    )


def make_run(model, workspace, max_steps=8):
    """返回 (run函数, events)。run(text) 走完整的 run_agent + trace 事件流。"""
    settings = make_settings(workspace)
    agent = build_agent(settings, model=model)
    session = SQLiteSession("test", db_path=":memory:")
    events: list[dict] = []

    async def _run(text):
        return await run_agent(
            agent, text, session=session, max_turns=max_steps, on_event=events.append
        )

    def run(text):
        return asyncio.run(_run(text))

    return run, events


ws = tempfile.mkdtemp(prefix="agent-test-")
Path(ws, "test.md").write_text("# 测试\n内容", encoding="utf-8")

# --- Test 3: read_file 正常读取，结果进入工具输出 ---
model = ScriptedModel([
    [function_call("read_file", {"path": "test.md"}, call_id="c1")],
    [assistant_message("已读取")],
])
run, events = make_run(model, ws)
answer = run("读取 test.md")
tool_ev = next(e for e in events if e["type"] == "tool_result")
check(
    "Test 3 read_file 正常读取",
    tool_ev["success"] and '"success": true' in tool_ev["result"] and answer == "已读取",
)

# --- Test 4: ~/.ssh 被拒绝 ---
model = ScriptedModel([
    [function_call("read_file", {"path": "~/.ssh/id_rsa"}, call_id="c1")],
    [assistant_message("无权访问该文件")],
])
run, events = make_run(model, ws)
answer = run("读取 ~/.ssh/id_rsa")
tool_ev = next(e for e in events if e["type"] == "tool_result")
check(
    "Test 4 ~/.ssh 被拒绝",
    not tool_ev["success"]
    and "permission_denied" in tool_ev["result"]
    and answer == "无权访问该文件",
)

# --- 路径逃逸组：symlink / .. / 同名前缀目录 ---
rf = make_read_file(ws)
outside = Path(ws).parent / f"{Path(ws).name}-backup"
outside.mkdir(exist_ok=True)
(outside / "secret.txt").write_text("secret")
Path(ws, "evil-link").unlink(missing_ok=True)
Path(ws, "evil-link").symlink_to(Path.home() / ".ssh")
check("逃逸: 符号链接", not rf("evil-link")["success"])
check("逃逸: .. 穿越", not rf("../../.." + str(outside / "secret.txt"))["success"])
check("逃逸: 同名前缀目录", not rf(str(outside / "secret.txt"))["success"])
check("逃逸后白名单内仍正常", rf("test.md")["success"])

# --- Test 5: 工具失败不崩溃，结构化错误回传 ---
model = ScriptedModel([
    [function_call("calculator", {"expression": "1+"}, call_id="c1")],
    [assistant_message("工具失败了，换一种方式")],
])
run, events = make_run(model, ws)
answer = run("触发失败")
tool_ev = next(e for e in events if e["type"] == "tool_result")
check(
    "Test 5 工具失败不崩溃",
    answer == "工具失败了，换一种方式"
    and not tool_ev["success"]
    and "calc_error" in tool_ev["result"],
)

# --- Test 7: 无限调用被 max_turns 终止 ---
def always_tool(call):
    return ModelStep(
        output=[function_call("calculator", {"expression": "1+1"}, call_id=f"c{len(call.input)}")]
    )


model = ScriptedModel([ModelStep.respond(always_tool)] * 10)
run, events = make_run(model, ws, max_steps=3)
answer = run("诱导无限循环")
check(
    "Test 7 MAX_STEPS 终止",
    "已达到最大执行步数（3）" in answer,
    answer,
)
check(
    "Test 7 stop 事件 + 工具摘要",
    any(e["type"] == "stop" and e["tools_used"] == ["calculator"] * 3 for e in events),
)

# --- web_fetch SSRF 静态校验（不发请求的分支）---
check("SSRF: file:// 拒绝", not web_fetch("file:///etc/passwd")["success"])
check("SSRF: 内网 IP 拒绝", not web_fetch("http://192.168.1.1/")["success"])
check("SSRF: metadata 地址拒绝", not web_fetch("http://169.254.169.254/")["success"])

# --- Trace 字段完整性（PRD §15）---
model = ScriptedModel([
    ModelStep(
        output=[function_call("read_file", {"path": "test.md"}, call_id="c1")],
        usage=Usage(requests=1, input_tokens=10, output_tokens=5, total_tokens=15),
    ),
    ModelStep(
        output=[assistant_message("总结完毕")],
        usage=Usage(requests=1, input_tokens=20, output_tokens=5, total_tokens=25),
    ),
])
run, events = make_run(model, ws)
run("读一下 test.md")
req_ev = next(e for e in events if e["type"] == "request")
check(
    "Trace: request 含 request_id/timestamp/user_input/model",
    all(k in req_ev for k in ("request_id", "timestamp", "user_input", "model"))
    and req_ev["user_input"] == "读一下 test.md",
)
llm_evs = [e for e in events if e["type"] == "llm"]
check(
    "Trace: llm 事件含 step/model/latency/usage，逐步记录",
    len(llm_evs) == 2
    and all(all(k in e for k in ("step", "model", "latency", "usage")) for e in llm_evs),
)
check(
    "Trace: 所有事件带同一 request_id",
    all(e.get("request_id") == req_ev["request_id"] for e in events),
)
tool_ev = next(e for e in events if e["type"] == "tool_call")
check(
    "Trace: tool_call 含 step/tool/arguments",
    all(k in tool_ev for k in ("step", "tool", "arguments"))
    and tool_ev["tool"] == "read_file",
)
final_ev = next(e for e in events if e["type"] == "final")
check(
    "Trace: final 累计各步 token_usage",
    final_ev["answer"] == "总结完毕"
    and final_ev["token_usage"]
    == {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
    f"实际: {final_ev.get('token_usage')}",
)

# --- LLM 错误：error 事件入 Trace 后继续上抛 ---
model = ScriptedModel([ModelStep.raise_error(RuntimeError("api 炸了"))])
run, events = make_run(model, ws)
try:
    run("x")
    raised = False
except RuntimeError:
    raised = True
err_ev = next((e for e in events if e["type"] == "error"), None)
check(
    "Trace: LLM 异常产生 error 事件后继续上抛",
    raised and err_ev is not None and err_ev["error"]["type"] == "RuntimeError",
)

# --- 时效性：dynamic instructions 注入真实当前日期 ---
model = ScriptedModel([[assistant_message("ok")]])
run, _ = make_run(model, ws)
run("今天有什么新闻")
sys_prompt = model.calls[0].system_instructions
check(
    "instructions 含当前真实日期时间",
    "当前日期时间" in sys_prompt and str(datetime.now().year) in sys_prompt,
)

# --- 会话历史：SQLiteSession 自动携带上一轮 ---
model = ScriptedModel([[assistant_message("第一轮")], [assistant_message("第二轮")]])
run, _ = make_run(model, ws)
run("第一轮问题")
run("第二轮问题")
second_input = json.dumps(model.calls[1].input, ensure_ascii=False, default=str)
check("Session 携带历史（第二轮调用包含第一轮内容）", "第一轮问题" in second_input)

# --- schema 生成：@function_tool 从签名自动生成（替代手搓 validate_arguments）---
schema = calculator.params_json_schema
check(
    "schema: 自动生成 required 与类型",
    schema["required"] == ["expression"]
    and schema["properties"]["expression"]["type"] == "string",
    json.dumps(schema, ensure_ascii=False),
)
check("instructions 基础文本保留", BASE_INSTRUCTIONS in _instructions(None, None))

# --- web_fetch 正文抽取精简 ---
html = """<html><head><title>t</title><style>x{}</style></head><body>
<nav>首页 城市列表 全国 北京 上海 广州</nav>
<script>var junk = 1;</script>
<main><h1>上海天气</h1><p>小雨转阴</p><p>17℃ ~ 22℃</p></main>
<aside>广告位 推荐阅读</aside>
<footer>备案信息 友情链接 关于我们</footer>
</body></html>"""
ex = _TextExtractor()
ex.feed(html)
text = ex.text()
check(
    "正文抽取: 跳过 nav/footer/aside/script 样板",
    all(j not in text for j in ("城市列表", "备案信息", "广告位", "junk")),
)
check("正文抽取: 保留主体内容", "上海天气" in text and "小雨转阴" in text)
check("正文抽取: 无连续空行", "\n\n" not in text)

ex2 = _TextExtractor()
ex2.feed(
    "<html><body>"
    "<div><a>北京</a> <a>上海</a> <a>广州</a> <a>深圳</a> <a>杭州</a></div>"
    "<p>明天小雨转阴，气温17到22度，出门记得带伞。</p>"
    "</body></html>"
)
t2 = ex2.text()
check(
    "正文抽取: 高链接密度导航块被通用丢弃（不写死网站）",
    "北京" not in t2 and "小雨转阴" in t2,
)

ex3 = _TextExtractor()
ex3.feed("<html><body><p>详见<a>这份报告</a>，明天小雨转阴，气温17到22度。</p></body></html>")
check("正文抽取: 含少量链接的正文不误杀", "小雨转阴" in ex3.text())

ex4 = _TextExtractor()
ex4.feed(
    "<html><body>"
    "<p>较易发 感冒指数 天凉，湿度大，较易感冒。</p>"
    "<p>中雨</p><p>中雨</p>"
    "<p>较易发 感冒指数 天凉，湿度大，较易感冒。</p>"
    "</body></html>"
)
t4 = ex4.text()
check("正文去重: 长模板行只留一次", t4.count("感冒指数") == 1)
check("正文去重: 短数据行不误删（每日天气可相同）", t4.count("中雨") == 2)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
