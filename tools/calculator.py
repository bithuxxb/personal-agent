import ast
import operator

from .base import Tool, ToolResult

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("只支持 + - * / % ** 和括号")


def _calculate(expression: str) -> ToolResult:
    try:
        value = _eval(ast.parse(expression, mode="eval"))
    except Exception as exc:
        return ToolResult(
            success=False, error={"type": "calc_error", "message": str(exc)}
        )
    return ToolResult(success=True, data={"expression": expression, "value": value})


tool = Tool(
    name="calculator",
    description="计算数学表达式的值，支持 + - * / % ** 和括号",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "数学表达式，例如 (3+4)*2",
            }
        },
        "required": ["expression"],
    },
    func=_calculate,
    permission_level=0,
)
