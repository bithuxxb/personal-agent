# Personal Agent 产品需求文档

> **实现状态更新**：本文档描述 v0.1 的设计，其中 Runtime/LLM/Registry 曾全部手搓实现并通过验收。
> 当前代码主线已切换为 **OpenAI Agents SDK 实现**（原 §22 v0.7 的对比重写提前执行）：
> tool loop、schema 校验、会话历史由 SDK 承担，手搓版代码已删除。
> 各章节中标注了「SDK 版现状」。保留手搓版的设计描述，作为对比材料。

## 1. 项目概述

### 1.1 产品名称

Personal Agent

暂定版本：

v0.1

### 1.2 产品定位

Personal Agent 是一个面向个人使用的 AI 智能体系统。

系统基于大语言模型和 Tool Calling 机制，使 AI 不仅能够回答问题，还能够根据用户请求自主判断是否需要调用外部工具，并综合工具返回的信息完成任务。

v0.1 重点不是实现高度自主的通用智能体，而是建立一个：

- 可控
- 可观察
- 可调试
- 可扩展
- 可持续演进

的个人 Agent Runtime。

---

## 2. 项目目标

注：这是一个个人学习项目，目的是一边动手实现、一边理解 Agent 的各个环节。本文档刻意保持精简，只写死少数会"咬人"的底线（路径逃逸、无限循环、API Key 泄露），其余细节留到实现过程中体验和迭代。

v0.1 需要验证以下核心能力：

1. LLM 可以正常完成多轮对话。
2. LLM 可以自主判断是否需要调用工具。
3. Agent 可以执行 Tool Calling Loop。
4. Agent 可以连续调用多个工具。
5. Agent 可以读取互联网实时信息。
6. Agent 可以读取本地文件。
7. Tool 调用过程完整可观察。
8. Tool 出错时 Agent 可以继续工作。
9. Agent 可以限制最大执行次数。
10. 工具调用具备基础权限控制能力。

---

## 3. 非目标

v0.1 暂不实现以下功能：

- 多 Agent 协作
- Autonomous Agent
- Browser Computer Use
- Shell 全权限执行
- 邮件自动发送
- Calendar 自动操作
- 向量数据库
- 完整 RAG Pipeline
- 长期语义 Memory
- MCP Server 管理
- Task Planner
- Reflection
- Self-Correction Framework
- 后台异步任务
- 多用户系统
- SaaS 化部署

这些能力在 Agent Runtime 稳定后逐步增加。

---

## 4. 目标用户

v0.1 仅服务单个用户。

主要使用场景包括：

- 技术问题查询
- 网络安全研究
- AI 技术研究
- 新闻和技术动态搜索
- 网页内容分析
- 本地技术文档读取
- 信息整理和总结

---

## 5. 核心使用场景

### 场景 1：普通对话

用户：

“解释一下什么是 Zero Trust。”

系统行为：

1. 接收用户输入。
2. LLM 判断不需要外部工具。
3. 直接生成回答。

执行路径：

User → LLM → Answer

---

### 场景 2：互联网搜索

用户：

“OpenAI 最近更新了哪些 Agent 相关能力？”

系统行为：

1. LLM 判断该问题具有时效性。
2. 调用 web_search。
3. 获取搜索结果。
4. 根据结果决定是否读取具体网页。
5. 必要时调用 web_fetch。
6. LLM 综合信息。
7. 返回最终结果。

执行路径：

User

→ LLM

→ web_search

→ LLM

→ web_fetch

→ LLM

→ Answer

---

### 场景 3：读取本地文件

用户：

“帮我总结这个项目里的 README。”

系统行为：

1. LLM 判断需要访问本地文件。
2. 调用 read_file。
3. 返回文件内容。
4. LLM 根据内容完成总结。

---

### 场景 4：工具失败

用户：

“读取这个 URL。”

当目标网页访问失败时：

1. Tool 返回结构化错误。
2. Agent 不崩溃。
3. LLM 根据错误决定：
   - 重试；
   - 换其他方式获取；
   - 或向用户说明失败原因。

---

## 6. 核心系统架构

系统逻辑架构：

User

↓

Interface

↓

Agent Runtime

↓

LLM

↓

Tool Calling

↓

Tool Registry

↓

Tool

↓

Tool Result

↓

LLM

↓

Final Response

---

## 7. Agent Runtime

Agent Runtime 是整个系统的核心。

其职责包括：

- 接收用户请求
- 管理消息上下文
- 调用 LLM
- 解析 Tool Call
- 调用 Tool Registry
- 获取 Tool Result
- 将结果重新发送给 LLM
- 控制执行循环
- 返回最终答案

> **SDK 版现状**：以上职责由 SDK 的 `Runner.run_streamed(..., max_turns=...)` 承担；
> 达到上限抛 `MaxTurnsExceeded`，由 `trace.py` 捕获并生成兜底输出。
> 本项目保留的 Runtime 层代码只有 `trace.py`（事件流映射）和 `agent.py`（组装）。

v0.1 手搓版基础执行逻辑（已由 SDK 接管，留档）：

```text
step = 0

while step < max_steps:

    step += 1    // 一步 = 一轮 LLM 调用及其工具调用

    调用 LLM

    if 没有 tool_call:
        返回最终答案

    执行 tool

    将 tool result 加入 context

达到 max_steps：

    停止执行，告知用户已达上限并附上已有信息
```

默认：

```text
MAX_STEPS = 8
```

该参数应该允许配置。

---

## 8. LLM 模块

LLM 模块负责所有模型通信。

职责：

- 模型 API 调用
- Tool Schema 注入
- System Prompt 注入（每次请求刷新当前真实日期时间，时效性判断不依赖模型知识截止日期）
- Message 格式转换
- Response 解析
- Tool Call 解析
- API Error 处理

> **SDK 版现状**：模型通信由 SDK 的 `Model` 层承担。DeepSeek 只兼容 Chat Completions
> （`/v1/chat/completions`），未实现 SDK 默认的 Responses API，因此用官方推荐的桥接：
> `OpenAIChatCompletionsModel(model=..., openai_client=AsyncOpenAI(base_url=...))`。
> System Prompt 的日期注入通过 SDK dynamic instructions（`instructions` 传函数）实现，
> 见 `agent.py` 的 `_instructions`。瞬时错误重试由 openai 客户端内建机制承担。

Agent Runtime 不直接依赖具体模型 API。

应该通过统一接口调用：

```text
LLMClient.generate()
```

方便未来增加：

- OpenAI
- Anthropic
- Gemini
- Local Model

---

## 9. Tool System

Tool 是 Agent 与外部系统交互的主要能力边界。

每个 Tool 至少包含：

```text
name
description
parameters schema
execute()
permission level
```

统一接口：

```text
Tool
├── metadata
├── schema
├── validate()
└── execute()
```

> **SDK 版现状**：工具用 `@function_tool` 声明，name/description 来自函数名与 docstring，
> parameters schema 由 SDK 从类型签名自动生成（pydantic），参数校验由 SDK 在调用前完成——
> 手搓版的 `Tool` dataclass 和 `validate_arguments` 退役。
> 工具本体仍是 `tools/` 下的普通 Python 函数，返回 `{success, data|error}` 结构。

---

## 10. Tool Registry

Tool Registry 管理所有可用工具。

职责：

- 注册 Tool
- 查询 Tool
- 输出 Tool Schema
- Tool 参数校验
- Tool 权限校验
- Tool 执行
- Tool Error 标准化

Agent Runtime 不直接调用具体 Tool。

调用方式：

```text
registry.execute(
    tool_name,
    arguments
)
```

> **SDK 版现状**：Registry 退役。工具在 `build_agent()` 时直接以列表交给 `Agent`；
> schema 输出、参数校验、错误标准化（异常不会直接抛给模型）均由 SDK 承担。
> 安全校验（目录白名单、SSRF）仍在工具函数内部，不依赖框架。

---

## 11. v0.1 Tool

### 11.1 web_search

功能：

根据关键词执行互联网搜索。

输入：

```json
{
  "query": "string"
}
```

输出：

```json
{
  "results": [
    {
      "title": "...",
      "url": "...",
      "snippet": "..."
    }
  ]
}
```

---

### 11.2 web_fetch

功能：

获取指定网页内容。

输入：

```json
{
  "url": "https://..."
}
```

输出：

```json
{
  "url": "...",
  "title": "...",
  "content": "..."
}
```

需要考虑：

- 超时
- 网页过大
- 非 HTML 内容
- 请求失败
- 重定向
- 正文精简：跳过样板元素（nav/footer/script 等）、按链接密度丢弃导航块（通用规则，不写死特定网站）、长重复行去重

---

### 11.3 read_file

功能：

读取本地文本文件。

输入：

```json
{
  "path": "..."
}
```

输出：

```json
{
  "path": "...",
  "content": "...",
  "truncated": false,
  "size_bytes": 12345
}
```

限制：

- 单文件最大读取 256 KB，超出部分截断并设置 `truncated: true`。
- 二进制文件或无法解码为 UTF-8 的文件返回结构化错误。

初期支持：

- TXT
- Markdown
- JSON
- YAML
- Python
- JavaScript
- TypeScript
- Shell
- 普通配置文件

v0.1 不要求支持：

- PDF
- Word
- Excel
- 图片 OCR

---

## 12. Tool 权限模型

工具按照风险级别分类。

### Level 0：无外部操作

例如：

```text
calculator
```

无需用户确认。

### Level 1：只读

例如：

```text
web_search
web_fetch
read_file
```

默认允许。

### Level 2：低风险写操作

例如：

```text
create_file
save_note
```

未来版本实现。

根据策略决定是否需要确认。

### Level 3：高风险操作

例如：

```text
shell
delete_file
send_email
execute_code
```

必须显式确认。

v0.1 默认不提供 Level 3 工具。

> **SDK 版现状**：手搓 registry 的 Level≥2 硬拦截已随 registry 退役。
> 现有工具全部为 Level 0/1，无实际拦截对象；未来引入 Level 2+ 工具时，
> 使用 SDK 的 tool approval 机制（`needs_approval`）替代自研权限级。

---

## 13. Context Management

v0.1 实现基本短期上下文管理。

Context 至少保存：

```text
system
user
assistant
tool_call
tool_result
```

需要支持：

- 连续多轮对话
- Tool Result 回传
- 最大上下文长度限制

当 Context 过大时：

v0.1 采用简单截断策略。唯一硬性规则：不得截断到 tool_call / tool_result 消息对的中间，否则模型 API 会直接报错。其余策略（保留几轮、怎么淘汰）在实现中体会后再调整。

暂不实现自动总结和复杂 Context Compression。

> **SDK 版现状**：会话历史由 SDK `SQLiteSession` 持久化（`sessions.db`）并自动回注，
> 手搓的组粒度截断已删除。SDK 默认不做长度截断——超长上下文如何治理留作后续体验点。

---

## 14. Memory

v0.1 不实现真正的 Long-Term Memory。

当前 Memory 等同于：

```text
Current Conversation Context
```

但是代码层需要预留：

```text
MemoryProvider
```

未来可以增加：

```text
SQLite Memory
Vector Memory
Profile Memory
Episodic Memory
```

---

## 15. Observability

所有 Agent 执行必须产生 Trace。

> **SDK 版现状**：Trace 事件由 `trace.py` 监听 SDK 的 stream 事件
> （`raw_response_event` / `run_item_stream_event`）映射生成，字段与下表一致，
> CLI 和 Web 前端不变。SDK 内建 tracing（上报 api.openai.com）已关闭——
> 它面向 OpenAI 平台，用第三方 key 会 401。

每次请求至少记录：

```text
request_id
timestamp
user_input
model
step
tool_name
tool_arguments
tool_result
latency
token_usage
error
final_response
```

tool_result 过大时可以在 Trace 中截断，避免日志被整页网页撑爆。

一个典型 Trace：

```text
Request #1024

USER
"OpenAI 最近有什么 Agent 更新？"

STEP 1
LLM

DECISION
tool_call

TOOL
web_search

ARGS
{
  "query": "OpenAI Agents latest update"
}

RESULT
...

STEP 2
LLM

TOOL
web_fetch

RESULT
...

STEP 3
LLM

FINAL
...
```

日志应该优先保证人可以直接阅读。

---

## 16. Error Handling

系统必须处理以下错误：

### LLM Error

包括：

- API Timeout
- Rate Limit
- Authentication Error
- Server Error

Agent Runtime 不应直接崩溃。

处理策略：Timeout / Rate Limit / 5xx 用指数退避重试，最多 3 次；Authentication Error 不重试，提示检查 API Key。

### Tool Error

统一返回：

```json
{
  "success": false,
  "error": {
    "type": "...",
    "message": "..."
  }
}
```

禁止直接将 Python Exception 暴露给 Agent。

### Agent Loop

如果执行超过：

```text
MAX_STEPS
```

必须终止。

终止时必须返回兜底输出：告知用户已达到最大执行步数，并附上目前已收集到的信息，而不是只返回错误。

避免：

```text
LLM
→ Tool
→ LLM
→ Tool
→ LLM
→ Tool
→ 无限循环
```

---

## 17. Security

v0.1 必须遵守最小权限原则。

### Local File

read_file 只能访问配置允许的目录（白名单机制，仅白名单生效）。

例如：

```text
~/Documents/AgentWorkspace
```

实现要点：路径先做 realpath 解析（展开 `~`、解析 `..` 和符号链接），再用路径包含关系（不是字符串前缀）判断是否在白名单目录内——否则 `/workspace-backup` 这类同名前缀目录会被误放行。

以下目录天然不在白名单内，默认不可访问：

```text
~/.ssh
~/.aws
~/Library
/etc
```

### Web

web_fetch 应考虑：

- SSRF
- localhost
- 私有 IP
- file://
- 非 HTTP 协议

需要限制：

```text
http://
https://
```

并阻止访问本地和私有网络地址。

实现要点：只允许 http/https；阻止 localhost 和内网 IP；重定向后要重新校验目标。更完整的 SSRF 防护（DNS rebinding、连接绑定等）留到实际需要时再加强。

---

## 18. 配置

系统配置通过环境变量和配置文件管理。

例如：

```text
LLM_API_KEY
LLM_BASE_URL
MODEL
MAX_STEPS
LOG_LEVEL
WORKSPACE_DIR
SEARCH_API_KEY
```

不得将 API Key 写入代码。

技术选型（已确定）：

- 语言：Python
- Agent 框架：OpenAI Agents SDK（原 v0.7 对比重写提前执行，已成为主线；v0.1 手搓 Runtime 已删除，设计留档于本文档）
- LLM：DeepSeek（OpenAI Chat Completions 兼容协议，经 `OpenAIChatCompletionsModel` 桥接，通过 LLM_BASE_URL 切换）
- 搜索：初期用 DuckDuckGo（免费、无需 Key）；web_search 可日后替换为 Tavily 等付费服务

---

## 19. 用户界面

v0.1 以 CLI 为主。

示例：

```text
$ agent

Personal Agent v0.1

> OpenAI 最近有什么 Agent 更新？

[thinking]

[tool]
web_search(...)

[tool]
web_fetch(...)

Assistant:
...
```

原因：

CLI 最有利于观察 Agent 内部执行过程。

同时提供一个实验性 Web UI（`web/`）：浏览器对话页面 + 最近一次请求的结构化 Trace 面板，复用同一个 AgentRuntime。Trace 数据来自 Runtime 发出的结构化事件，CLI 和 Web 只是两种订阅者。

---

## 20. 项目阶段

### Milestone 1

LLM Chat

完成：

```text
User → LLM → Answer
```

### Milestone 2

Tool Calling

完成：

```text
User
→ LLM
→ Tool
→ LLM
→ Answer
```

同时实现最小 Trace 骨架（打印每一步的 tool_call 与结果摘要），否则后续里程碑无法调试。

### Milestone 3

Tool Registry

实现：

```text
Web Search
Web Fetch
Local File
```

### Milestone 4

Agent Runtime

实现：

- Multi-step Tool Calling
- MAX_STEPS
- Error Handling

### Milestone 5

Observability

在 M2 的 Trace 骨架基础上完善：

- 完整 Trace 字段（见 §15）
- Tool Log
- Error Log
- Latency
- Token Usage

### Milestone 6

Security

实现：

- Tool Permission
- Workspace Restriction
- URL Security Validation

v0.1 完成。

---

## 21. v0.1 验收标准

系统需要通过以下测试。

所有测试以 Trace 记录为判定依据。Test 1、2 靠真实模型人工核对；Test 3–7 及路径逃逸、SSRF 边角、schema 生成、正文抽取、日期注入、会话持久化等已实现为自动化契约测试（SDK `ScriptedModel` 脚本回放，不依赖真实模型）：`.venv/bin/python tests/acceptance.py`。

### Test 1

输入：

“什么是 XSS？”

预期：

Trace 中不出现任何 tool_call。

### Test 2

输入：

“今天 OpenAI 有什么新消息？”

预期：

Trace 中出现 tool_name = web_search。

### Test 3

输入：

“读取 workspace 下的 test.md。”

预期：

Trace 中出现 tool_name = read_file，且最终回答基于文件内容。

### Test 4

输入：

“读取 ~/.ssh/id_rsa。”

预期：

read_file 返回结构化权限错误，文件内容不进入 Context，Agent 向用户说明拒绝原因。

### Test 5

Search API 失败（通过注入故障模拟）。

预期：

Agent 不崩溃，Trace 中记录标准化 Tool Error，最终回复向用户说明失败情况。

### Test 6

输入：

“搜索 <某话题> 的最新消息，并读取搜索结果中第一个链接的内容。”

预期：

Trace 中依次出现 web_search 和 web_fetch，且最终回答综合了两次工具调用的结果。

### Test 7

构造诱导无限调用的输入。

预期：

达到 MAX_STEPS 后强制终止，返回兜底输出（说明已达上限并附已有信息），Trace 记录终止原因。

---

## 22. 后续 Roadmap

### v0.2

加入：

- URL Reader 增强
- Structured Output
- ~~Conversation Storage~~（已由 SDK `SQLiteSession` 顺带获得）
- ~~SQLite~~（同上）

### v0.3

加入：

- Long-Term Memory
- User Profile
- Memory Retrieval

### v0.4

加入：

- MCP Client
- MCP Tools

### v0.5

加入：

- Task Planner
- Task State
- 任务级重试与恢复（区别于 v0.1 的 API 瞬时错误重试）
- Resume

### v0.6

加入：

- Browser Automation
- Computer Use

### v0.7（已完成，提前执行）

根据复杂度重新评估：

- LangGraph
- PydanticAI
- OpenAI Agents SDK
- 自研 Runtime

是否需要引入更高级 Agent Framework。

**结论：已用 OpenAI Agents SDK 重写为主线。** 对比结论：

SDK 封装掉的（约 400 行手搓代码退役）：

- tool calling 循环与 max_turns 上限（`Runner` + `MaxTurnsExceeded`）
- 工具 schema 生成与参数运行时校验（`@function_tool` + pydantic）
- 消息历史管理与持久化（`SQLiteSession`，顺带完成原 v0.2 的对话存储）
- LLM 瞬时错误重试（openai 客户端内建）
- usage 统计

仍然自己保留的：

- dynamic instructions 注入真实日期时间（时效性问题，框架不管）
- 工具安全校验：目录白名单 realpath 判定、SSRF 防护（框架不管业务安全）
- 正文精简抽取（链接密度过滤、长行去重）
- 自有 trace 事件流（SDK 内建 tracing 绑死 OpenAI 平台，第三方模型不可用）

失去的观察点：

- context 截断策略不再由自己控制（SDK 默认不截断，超长治理待体验）
- LLM 重试过程不再逐次入 trace（openai 客户端内部完成）

---

## 23. 核心设计原则

Personal Agent 的首要设计原则不是自主性，而是可控性。

优先级：

```text
可控
>
可观察
>
可靠
>
可扩展
>
自主
```

任何新增能力都必须首先回答：

1. 为什么需要这个能力？
2. LLM 是否真的应该拥有这个权限？
3. 失败时如何恢复？
4. 如何观察它做了什么？
5. 如何阻止错误行为？
6. 是否可以用更简单的方式解决？

只有在这些问题解决之后，才增加 Agent 的自主程度。
