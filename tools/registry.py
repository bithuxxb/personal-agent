from .base import Tool, ToolResult


class ToolRegistry:
    """PRD §10。M2 先用最简实现：注册、出 schema、按名执行。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                error={"type": "unknown_tool", "message": f"未知工具: {name}"},
            )
        return tool.execute(arguments)
