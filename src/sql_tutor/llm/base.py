from abc import ABC, abstractmethod

from sql_tutor.llm.models import LLMRequest, LLMResponse


class LLMProviderError(RuntimeError):
    """Raised when a provider cannot return a usable response."""


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError