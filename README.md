# Personal Agent

一个个人 AI 智能体的学习型项目。v0.1 手搓了完整的 Agent Runtime（tool calling 循环、工具注册表、上下文管理、权限控制）；当前主线已切换为 **OpenAI Agents SDK** 实现（原 roadmap 的 v0.7 对比重写），亲身体验框架到底封装了什么。

详细设计见 [personal-agent-v0.1-PRD.md](personal-agent-v0.1-PRD.md)。

## SDK 替手搓版封装了什么

| v0.1 手搓 | SDK 版 |
|---|---|
| `runtime/loop.py` tool calling 循环、MAX_STEPS | `Runner.run_streamed(..., max_turns=...)` + `MaxTurnsExceeded` |
| `tools/base.py` schema 声明 + `validate_arguments` | `@function_tool` 从类型签名自动生成 schema 并校验 |
| `tools/registry.py` 注册/查找/权限拦截 | Agent 构造时的 tools 列表（权限审批由 SDK tool approval 机制承担，暂未启用） |
| `llm/client.py` 重试退避、usage 统计 | openai 客户端内建重试 + SDK usage 汇总 |
| context 截断、历史管理 | `SQLiteSession`（顺带拿到了原 v0.2 计划的对话持久化） |

仍然自己负责的：dynamic instructions 注入真实日期时间（`agent.py`）、工具安全校验（目录白名单、SSRF 防护）、正文精简抽取、trace 事件流（`trace.py`，CLI/Web 共用）。

## 功能

- 多轮对话（DeepSeek / OpenAI，OpenAI 兼容协议任意切换；SDK 走 `OpenAIChatCompletionsModel` 桥接）
- Tool Calling 循环：模型自主判断并连续调用多个工具，带 max_turns 保护
- 内置工具：`calculator`、`web_search`（DuckDuckGo，免 Key）、`web_fetch`（SSRF 防护 + 正文精简：链接密度过滤、长行去重）、`read_file`（目录白名单）
- 时效性保障：instructions 每次运行注入真实日期时间，不依赖模型知识截止日期
- 会话持久化：SDK `SQLiteSession`（`sessions.db`，CLI 与 Web 各自独立会话）
- 结构化 Trace：request_id、工具调用、延迟、token 用量、错误事件全链路记录
- 双界面：CLI + Web UI（对话 + Trace 面板）
- 29 项自动化验收测试（SDK `ScriptedModel` 回放，确定性可重复）

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 创建 .env：
#   LLM_API_KEY=sk-...            # DeepSeek 平台申请
#   LLM_BASE_URL=https://api.deepseek.com
#   MODEL=deepseek-flash

./start.sh        # Web UI → http://127.0.0.1:8765
./start.sh cli    # CLI 模式
```

## 运行验收测试

```bash
.venv/bin/python tests/acceptance.py
```

## 项目结构

```
main.py            CLI 入口（asyncio + SQLiteSession）
start.sh           启动脚本（web / cli）
config.py          环境变量配置
agent.py           SDK Agent 组装：模型桥接、dynamic instructions、@function_tool 工具
trace.py           SDK stream 事件 → PRD §15 trace 事件流（CLI/Web 共用）
tools/             工具实现：calculator、web（search/fetch）、local_file（白名单）
web/server.py      FastAPI 服务（/api/chat、/api/traces）
web/static/        Web UI 单页
tests/acceptance.py  PRD §21 验收测试
```

## 设计原则

可控 > 可观察 > 可靠 > 可扩展 > 自主。所有工具默认只读，文件访问限定白名单目录，网页抓取拒绝内网地址。

## Roadmap

v0.2+ 计划：Structured Output、长期记忆、MCP 客户端、任务规划。SDK 重写（原 v0.7）已完成，对话持久化（原 v0.2 一部分）由 SDK Session 顺带获得。
