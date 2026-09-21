import json
import urllib.error
import urllib.request

from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.http import post_json
from sql_tutor.llm.models import LLMRequest, LLMResponse


def list_models(
    base_url: str = "http://localhost:11434",
    *,
    timeout_seconds: float = 10.0,
) -> tuple[str, ...]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/tags",
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(1_000_001)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise LLMProviderError(
            f"Could not reach Ollama at {base_url}: {error}"
        ) from error

    if len(body) > 1_000_000:
        raise LLMProviderError("Ollama model list is too large")

    try:
        payload = json.loads(body)
        models = payload["models"]
        names = tuple(model["name"] for model in models)
    except (json.JSONDecodeError, KeyError, TypeError, IndexError) as error:
        raise LLMProviderError("Unexpected Ollama model list response") from error

    if not all(isinstance(name, str) and name for name in names):
        raise LLMProviderError("Unexpected Ollama model name")
    return names


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
