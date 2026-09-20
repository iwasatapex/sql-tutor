import json
from urllib.request import Request, urlopen

from sql_tutor.llm.base import LLMProvider
from sql_tutor.llm.models import LLMRequest, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    """Minimal provider for OpenAI-compatible chat completion endpoints."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def generate(self, request: LLMRequest) -> LLMResponse:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        http_request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urlopen(http_request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode())
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage")
        return LLMResponse(content=content, model=self.model, usage=usage)
