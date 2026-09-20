from abc import ABC, abstractmethod

from sql_tutor.llm.models import LLMRequest, LLMResponse


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError