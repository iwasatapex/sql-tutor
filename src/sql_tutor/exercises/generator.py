import json

from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    TableColumn,
    TableSchema,
)
from sql_tutor.exercises.validator import validate_exercise
from sql_tutor.llm.base import LLMProvider
from sql_tutor.llm.models import LLMRequest


class ExerciseGenerationError(ValueError):
    """Raised when an LLM-generated exercise is invalid."""


class ExerciseGenerator:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def generate(
        self,
        concept: str,
        difficulty: ExerciseDifficulty,
    ) -> Exercise:
        request = LLMRequest(
            system_prompt=(
                "Generate one SQL exercise as valid JSON. "
                "Return only JSON without Markdown."
            ),
            prompt=(
                f"Generate a {difficulty.value} SQL exercise "
                f"about {concept}. "
                "Include exercise_id, title, description, "
                "concept, difficulty, schema, and expected_query."
            ),
        )

        response = self.provider.generate(request)

        try:
            payload = json.loads(response.content)
            exercise = self._parse_exercise(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ExerciseGenerationError(
                f"Invalid generated exercise: {error}"
            ) from error

        validation = validate_exercise(exercise)

        if not validation.is_valid:
            raise ExerciseGenerationError(
                "Exercise validation failed: "
                + "; ".join(validation.errors)
            )

        return exercise

    @staticmethod
    def _parse_exercise(payload: dict) -> Exercise:
        schema = tuple(
            TableSchema(
                name=table["name"],
                columns=tuple(
                    TableColumn(
                        name=column["name"],
                        data_type=column["data_type"],
                    )
                    for column in table["columns"]
                ),
            )
            for table in payload["schema"]
        )

        return Exercise(
            exercise_id=payload["exercise_id"],
            title=payload["title"],
            description=payload["description"],
            concept=payload["concept"],
            difficulty=ExerciseDifficulty(payload["difficulty"]),
            schema=schema,
            expected_query=payload["expected_query"],
            setup_statements=tuple(payload.get("setup_statements", ())),
        )
