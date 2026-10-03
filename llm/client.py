from openai import OpenAI


class LLMClient:
    """统一的模型调用入口（PRD §8）。M1 只做纯对话，tool schema 注入在 M2 加入。"""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, messages: list[dict]) -> str:
        resp = self._client.chat.completions.create(
            model=self.model, messages=messages
        )
        return resp.choices[0].message.content or ""
