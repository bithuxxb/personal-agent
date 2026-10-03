# Personal Agent v0.1

一个手搓的个人 AI 智能体——基于 LLM + Tool Calling 的学习型项目。不依赖任何 Agent 框架，Agent Runtime 循环、工具注册表、上下文管理、权限控制全部自己实现，用来理解智能体的每个环节到底是怎么工作的。

详细设计见 [personal-agent-v0.1-PRD.md](personal-agent-v0.1-PRD.md)。

## 功能

- 多轮对话（DeepSeek / OpenAI，OpenAI 兼容协议任意切换）
- Tool Calling 循环：模型自主判断并连续调用多个工具，带 MAX_STEPS 保护
- 内置工具：`calculator`、`web_search`（DuckDuckGo，免 Key）、`web_fetch`（SSRF 防护）、`read_file`（目录白名单）
- 结构化 Trace：每次请求的完整执行过程（工具调用、延迟、token 用量）
- 双界面：CLI + 实验性 Web UI（对话 + Trace 面板）
- 19 项自动化验收测试（mock LLM，确定性可重复）

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 配置：参考仓库里的代码注释，或直接创建 .env：
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
main.py            CLI 入口
start.sh           启动脚本（web / cli）
config.py          环境变量配置
llm/client.py      统一 LLM 调用入口（重试、token 统计）
runtime/loop.py    Agent Runtime：tool calling 循环、MAX_STEPS、context 截断
tools/             工具系统：base（Tool/ToolResult）、registry（权限校验）、四个工具
web/server.py      FastAPI 服务（/api/chat、/api/traces）
web/static/        Web UI 单页
tests/acceptance.py  PRD §21 验收测试
```

## 设计原则

可控 > 可观察 > 可靠 > 可扩展 > 自主。所有工具默认只读，文件访问限定白名单目录，网页抓取拒绝内网地址。

## Roadmap

v0.2+ 计划：对话持久化（SQLite）、长期记忆、MCP 客户端、任务规划。v0.7 用 OpenAI Agents SDK 重写一版做对比——看看手搓的这些代码框架到底封装了多少。
