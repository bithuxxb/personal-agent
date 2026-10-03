from dataclasses import dataclass
from typing import Any, Callable

_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validate_arguments(schema: dict, arguments: dict) -> str | None:
    """按 Tool.parameters 的 JSON Schema 子集校验参数（PRD §9 validate()）。
    返回错误消息；None 表示通过。"""
    if not isinstance(arguments, dict):
        return "参数必须是 JSON 对象"
    for key in schema.get("required", []):
        if key not in arguments:
            return f"缺少必填参数: {key}"
    props = schema.get("properties", {})
    for key, value in arguments.items():
        spec = props.get(key)
        if spec is None:
            return f"未知参数: {key}"
        expected = _TYPES.get(spec.get("type"))
        if expected and not isinstance(value, expected):
            return f"参数 {key} 类型错误: 期望 {spec.get('type')}，实际 {type(value).__name__}"
    return None


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
        if err := validate_arguments(self.parameters, arguments):
            return ToolResult(
                success=False, error={"type": "invalid_arguments", "message": err}
            )
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
