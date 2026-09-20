from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    system_prompt: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1024
    json_mode: bool = False


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    usage: dict[str, Any] | None = None
