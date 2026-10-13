"""SDK 版 Agent 组装。

对比 v0.1 手搓版，以下职责移交给了 OpenAI Agents SDK：
tool calling 循环（Runner）、tool schema 生成与参数校验（@function_tool + pydantic）、
会话历史（SQLiteSession）、max_turns 上限与兜底（MaxTurnsExceeded）、usage 统计。

仍然由本项目自己负责的：
dynamic instructions 注入真实日期时间、工具的安全校验（白名单/SSRF）、
trace 事件流（trace.py，喂给 CLI 打印和 Web Trace 面板）。
"""

from datetime import datetime
from pathlib import Path

from agents import Agent, OpenAIChatCompletionsModel, function_tool, set_tracing_disabled
from openai import AsyncOpenAI

from config import Settings
from tools.calculator import calculate as _calculate
from tools.local_file import make_read_file
from tools.web import web_fetch as _web_fetch
from tools.web import web_search as _web_search

BASE_INSTRUCTIONS = (
    "你是一个个人技术助手，回答简洁准确。"
    "需要计算时用 calculator；需要实时信息时用 web_search，"
    "需要读网页正文时用 web_fetch；需要读本地文件时用 read_file。"
)


def _instructions(context, agent) -> str:
    """dynamic instructions：每次运行都回调，注入真实当前日期时间。
    模型知识有截止日期，"今天/最近"类请求不能靠它自己推算。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
    return (
        f"{BASE_INSTRUCTIONS}\n\n"
        f"当前日期时间：{now}。"
        f"涉及“今天”“最近”“最新”等时效性请求时，以此日期为准生成搜索关键词。"
    )


@function_tool
def calculator(expression: str) -> dict:
    """计算数学表达式的值，支持 + - * / % ** 和括号。"""
    return _calculate(expression)


@function_tool
def web_search(query: str) -> dict:
    """根据关键词搜索互联网，返回标题、链接和摘要。用于查询实时信息。"""
    return _web_search(query)


@function_tool
def web_fetch(url: str) -> dict:
    """获取指定网页的正文内容。仅支持 http/https，内网地址会被拒绝。"""
    return _web_fetch(url)


def build_agent(settings: Settings, model=None) -> Agent:
    # SDK 默认把 trace 上报 api.openai.com，第三方 key 会 401，关闭之
    set_tracing_disabled(True)
    if model is None:
        client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.base_url)
        # DeepSeek 只兼容 Chat Completions，不支持 SDK 默认的 Responses API
        model = OpenAIChatCompletionsModel(model=settings.model, openai_client=client)

    workspace = Path(settings.workspace_dir).expanduser().resolve()
    _read_file = make_read_file(settings.workspace_dir)

    @function_tool(
        description_override=(
            f"读取本地文本文件。只允许访问 {workspace} 目录下的文件；相对路径以该目录为基准。"
        )
    )
    def read_file(path: str) -> dict:
        return _read_file(path)

    return Agent(
        name="personal-agent",
        instructions=_instructions,
        model=model,
        tools=[calculator, web_search, web_fetch, read_file],
    )
