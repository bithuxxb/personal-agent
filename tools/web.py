import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from .base import Tool, ToolResult

TIMEOUT = 15
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_CONTENT_CHARS = 8000


def _validate_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"仅支持 http/https，实际协议: {parsed.scheme or '(缺失)'}"
    host = parsed.hostname
    if not host:
        return "URL 缺少主机名"
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return f"域名解析失败: {exc}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return f"目标解析到内网/保留地址 {ip}，已拒绝"
    return None


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = 0
        self._in_title = False
        self.title = ""
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
        if not self._skip:
            text = data.strip()
            if text:
                self.parts.append(text + " ")


def _web_search(query: str) -> ToolResult:
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = [
                {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
                for r in ddgs.text(query, max_results=5)
            ]
    except Exception as exc:
        return ToolResult(
            success=False, error={"type": "search_error", "message": str(exc)}
        )
    return ToolResult(success=True, data={"results": results})


def _web_fetch(url: str) -> ToolResult:
    current = url
    try:
        resp = None
        for _ in range(MAX_REDIRECTS + 1):
            if err := _validate_url(current):
                return ToolResult(
                    success=False, error={"type": "url_blocked", "message": err}
                )
            resp = httpx.get(current, timeout=TIMEOUT, follow_redirects=False)
            if resp.is_redirect:
                current = urljoin(current, resp.headers["location"])
                continue
            break
        else:
            return ToolResult(
                success=False,
                error={"type": "too_many_redirects", "message": f"超过 {MAX_REDIRECTS} 次重定向"},
            )

        if resp.status_code >= 400:
            return ToolResult(
                success=False,
                error={"type": "http_error", "message": f"HTTP {resp.status_code}"},
            )
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type:
            return ToolResult(
                success=False,
                error={"type": "non_html", "message": f"非 HTML 内容: {content_type}"},
            )
        if len(resp.content) > MAX_BODY_BYTES:
            return ToolResult(
                success=False,
                error={"type": "too_large", "message": "网页超过 2MB，未读取"},
            )

        extractor = _TextExtractor()
        extractor.feed(resp.text)
        content = "".join(extractor.parts)
        truncated = len(content) > MAX_CONTENT_CHARS
        return ToolResult(
            success=True,
            data={
                "url": str(resp.url),
                "title": extractor.title,
                "content": content[:MAX_CONTENT_CHARS],
                "truncated": truncated,
            },
        )
    except httpx.TimeoutException:
        return ToolResult(
            success=False,
            error={"type": "timeout", "message": f"请求超过 {TIMEOUT}s"},
        )
    except httpx.HTTPError as exc:
        return ToolResult(
            success=False, error={"type": "fetch_error", "message": str(exc)}
        )


web_search = Tool(
    name="web_search",
    description="根据关键词搜索互联网，返回标题、链接和摘要。用于查询实时信息。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"],
    },
    func=_web_search,
    permission_level=1,
)

web_fetch = Tool(
    name="web_fetch",
    description="获取指定网页的正文内容。仅支持 http/https，内网地址会被拒绝。",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要读取的网页 URL"}
        },
        "required": ["url"],
    },
    func=_web_fetch,
    permission_level=1,
)
