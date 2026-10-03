from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: dict | None = None

    def to_dict(self) -> dict:
        out = {"success": self.success}
        if self.success:
            out["data"] = self.data
        else:
            out["error"] = self.error
        return out


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., ToolResult]
    permission_level: int = 0

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, arguments: dict) -> ToolResult:
        try:
            return self.func(**arguments)
        except TypeError as exc:
            return ToolResult(
                success=False,
                error={"type": "invalid_arguments", "message": str(exc)},
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error={"type": "tool_error", "message": str(exc)},
            )
