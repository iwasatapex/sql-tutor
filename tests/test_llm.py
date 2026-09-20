from sql_tutor.llm.mock import MockLLMProvider
from sql_tutor.llm.models import LLMRequest


def test_mock_provider_returns_response() -> None:
    provider = MockLLMProvider(response="SELECT * FROM users;")

    response = provider.generate(
        LLMRequest(prompt="Write a SQL query.")
    )

    assert response.content == "SELECT * FROM users;"
    assert response.model == "mock"
