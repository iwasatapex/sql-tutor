from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.http import post_json
from sql_tutor.llm.models import LLMRequest, LLMResponse


class OllamaProvider(LLMProvider):
    """Local Ollama server via its native /api/chat endpoint."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
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
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        if request.json_mode:
            payload["format"] = "json"

        data = post_json(
            f"{self.base_url}/api/chat",
            payload,
            timeout=self.timeout_seconds,
        )

        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as error:
            raise LLMProviderError(
                f"Unexpected Ollama response: {str(data)[:200]}"
            ) from error

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            usage={
                "prompt_tokens": data.get("prompt_eval_count"),
                "completion_tokens": data.get("eval_count"),
            },
        )
