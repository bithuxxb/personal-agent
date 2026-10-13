from pathlib import Path

MAX_FILE_BYTES = 256 * 1024


def make_read_file(workspace_dir: str):
    """返回一个绑定 workspace 白名单的 read_file 函数。
    路径先 realpath 解析（展开 ~、解析 .. 和符号链接），再判断是否落在白名单目录内。"""
    root = Path(workspace_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    def read_file(path: str) -> dict:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        real = candidate.resolve()

        if not real.is_relative_to(root):
            return {
                "success": False,
                "error": {
                    "type": "permission_denied",
                    "message": f"路径不在允许目录内（{root}）: {path}",
                },
            }
        if not real.is_file():
            return {
                "success": False,
                "error": {"type": "not_found", "message": f"文件不存在: {path}"},
            }

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
                    return {
                        "success": False,
                        "error": {
                            "type": "decode_error",
                            "message": "文件不是有效的 UTF-8 文本",
                        },
                    }
        return {
            "success": True,
            "data": {
                "path": str(real),
                "content": content,
                "truncated": truncated,
                "size_bytes": size,
            },
        }

    return read_file
