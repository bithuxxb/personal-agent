import time

from openai import (
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)


class LLMClient:
    """统一的模型调用入口（PRD §8），含 §16 的重试策略：
    Timeout / Rate Limit / 5xx 指数退避最多 3 次，Authentication Error 不重试。"""

    def __init__(self, api_key: str, model: str, base_url: str | None = None, max_retries: int = 3, on_retry=None):
        self.model = model
        self.max_retries = max_retries
        # 每次退避重试前回调 on_retry(attempt, exc)，由 AgentRuntime 接管记入 trace
        self.on_retry = on_retry
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, messages: list[dict], tools: list[dict] | None = None):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._client.chat.completions.create(**kwargs)
                usage = None
                if resp.usage:
                    usage = {
                        "prompt_tokens": resp.usage.prompt_tokens,
                        "completion_tokens": resp.usage.completion_tokens,
                        "total_tokens": resp.usage.total_tokens,
                    }
                return resp.choices[0].message, usage
            except AuthenticationError:
                raise
            except (APITimeoutError, RateLimitError) as exc:
                if attempt >= self.max_retries:
                    raise
                if self.on_retry:
                    self.on_retry(attempt, exc)
                time.sleep(2 ** (attempt - 1))
            except APIStatusError as exc:
                if exc.status_code < 500 or attempt >= self.max_retries:
                    raise
                if self.on_retry:
                    self.on_retry(attempt, exc)
                time.sleep(2 ** (attempt - 1))
