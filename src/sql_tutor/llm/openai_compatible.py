from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.http import post_json
from sql_tutor.llm.models import LLMRequest, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    """Any server that speaks POST {base_url}/chat/completions.

    Works with llama.cpp's server, LM Studio, vLLM, OpenRouter, OpenAI,
    and Ollama's /v1 endpoint. ``base_url`` should include the version
    prefix, e.g. ``http://localhost:8080/v1``.
    """

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def generate(self, request: LLMRequest) -> LLMResponse:
        messages = []

        if request.system_prompt:
            messages.append(
                {"role": "system", "content": request.system_prompt}
            )

        messages.append({"role": "user", "content": request.prompt})

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = post_json(
            f"{self.base_url}/chat/completions",
            payload,
            headers=headers,
            timeout=self.timeout_seconds,
        )

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMProviderError(
                f"Unexpected response: {str(data)[:200]}"
            ) from error

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            usage=data.get("usage"),
        )
