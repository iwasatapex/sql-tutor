from __future__ import annotations

from sql_tutor.exercises.models import Exercise
from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.models import LLMRequest
from sql_tutor.tutor.hints import Hint


class LLMHintService:
    """Generate optional teaching hints while preserving deterministic fallback."""

    _SYSTEM_PROMPT = (
        "You are a patient SQL tutor. Give one concise hint, not the answer. "
        "Do not provide a complete SQL query. Focus on the learner's next step."
    )

    def __init__(self, provider: LLMProvider, fallback) -> None:
        self.provider = provider
        self.fallback = fallback

    def get_hint(
        self,
        exercise: Exercise,
        level: int,
        student_query: str | None = None,
    ) -> Hint:
        fallback_hint = self.fallback.get_hint(exercise.concept, level)
        prompt = self._build_prompt(exercise, level, student_query)
        try:
            response = self.provider.generate(
                LLMRequest(
                    system_prompt=self._SYSTEM_PROMPT,
                    prompt=prompt,
                    temperature=0.2,
                    max_tokens=160,
                )
            )
            message = " ".join(response.content.split())
            if not message or len(message) > 500:
                return fallback_hint
            if "```" in message or message.rstrip().endswith(";"):
                return fallback_hint
            return Hint(level=level, message=message)
        except (LLMProviderError, ValueError, TypeError):
            return fallback_hint

    @staticmethod
    def _build_prompt(
        exercise: Exercise,
        level: int,
        student_query: str | None,
    ) -> str:
        schema = "\n".join(
            f"{table.name}: "
            + ", ".join(column.name for column in table.columns)
            for table in exercise.schema
        )
        query = student_query or "No query submitted yet."
        return (
            f"Concept: {exercise.concept}\n"
            f"Difficulty: {exercise.difficulty.value}\n"
            f"Task: {exercise.description}\n"
            f"Schema:\n{schema}\n"
            f"Learner query:\n{query}\n"
            f"Hint level: {level}\n"
            "Respond with only one actionable hint."
        )
