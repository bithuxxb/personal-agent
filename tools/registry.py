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
        if tool.permission_level >= 2:
            return ToolResult(
                success=False,
                error={
                    "type": "permission_denied",
                    "message": f"工具 {name} 权限级为 Level {tool.permission_level}，v0.1 不提供此类工具的执行",
                },
            )
        return tool.execute(arguments)
