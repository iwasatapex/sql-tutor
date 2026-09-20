from sql_tutor.llm.base import LLMProvider
from sql_tutor.llm.models import LLMRequest, LLMResponse


class MockLLMProvider(LLMProvider):
    def __init__(self, response: str = "Mock response") -> None:
        self.response = response

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=self.response,
            model="mock",
        )
