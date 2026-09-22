from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    TableColumn,
    TableSchema,
)
from sql_tutor.llm.base import LLMProvider
from sql_tutor.llm.models import LLMRequest, LLMResponse
from sql_tutor.tutor.hints import HintService
from sql_tutor.tutor.llm_hints import LLMHintService


class FakeProvider(LLMProvider):
    def __init__(self, content: str) -> None:
        self.content = content
        self.request: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.request = request
        return LLMResponse(content=self.content, model="fake")


def exercise() -> Exercise:
    return Exercise(
        exercise_id="hint-1",
        title="Filter users",
        description="Return active users.",
        concept="WHERE",
        difficulty=ExerciseDifficulty.BEGINNER,
        schema=(TableSchema("users", (TableColumn("id", "INTEGER"),)),),
        expected_query="SELECT id FROM users WHERE active = 1;",
    )


def test_llm_hint_service_uses_model_hint() -> None:
    provider = FakeProvider("Check the condition used to filter rows.")
    service = LLMHintService(provider, HintService())

    result = service.get_hint(exercise(), 1, "SELECT id FROM users;")

    assert result.message == "Check the condition used to filter rows."
    assert provider.request is not None
    assert "SELECT id FROM users;" in provider.request.prompt


def test_llm_hint_service_rejects_query_like_output() -> None:
    provider = FakeProvider("SELECT id FROM users;")
    service = LLMHintService(provider, HintService())

    result = service.get_hint(exercise(), 1)

    assert result.message == HintService().get_hint("WHERE", 1).message
