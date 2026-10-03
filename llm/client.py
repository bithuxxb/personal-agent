from openai import OpenAI


class LLMClient:
    """统一的模型调用入口（PRD §8）。M2 起支持 tool schema 注入与 tool_call 解析。"""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, messages: list[dict], tools: list[dict] | None = None):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message
