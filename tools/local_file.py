from pathlib import Path

from .base import Tool, ToolResult

MAX_FILE_BYTES = 256 * 1024


def make_tool(workspace_dir: str) -> Tool:
    root = Path(workspace_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    def read_file(path: str) -> ToolResult:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        real = candidate.resolve()

        if not real.is_relative_to(root):
            return ToolResult(
                success=False,
                error={
                    "type": "permission_denied",
                    "message": f"路径不在允许目录内（{root}）: {path}",
                },
            )
        if not real.is_file():
            return ToolResult(
                success=False,
                error={"type": "not_found", "message": f"文件不存在: {path}"},
            )

        size = real.stat().st_size
        raw = real.read_bytes()[:MAX_FILE_BYTES]
        truncated = size > MAX_FILE_BYTES

        content = None
        for trim in range(0, 4):
            try:
                content = raw[: len(raw) - trim].decode("utf-8")
                break
            except UnicodeDecodeError:
                if not truncated:
                    return ToolResult(
                        success=False,
                        error={
                            "type": "decode_error",
                            "message": "文件不是有效的 UTF-8 文本",
                        },
                    )
        return ToolResult(
            success=True,
            data={
                "path": str(real),
                "content": content,
                "truncated": truncated,
                "size_bytes": size,
            },
        )

    return Tool(
        name="read_file",
        description=f"读取本地文本文件。只允许访问 {root} 目录下的文件；相对路径以该目录为基准。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径（相对或绝对）"}
            },
            "required": ["path"],
        },
        func=read_file,
        permission_level=1,
    )
