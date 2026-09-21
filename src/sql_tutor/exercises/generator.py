import json
import logging
import re

from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    TableColumn,
    TableSchema,
)
from sql_tutor.exercises.validator import validate_exercise
from sql_tutor.exercises.verifier import verify_exercise
from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.models import LLMRequest

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a rigorous SQL curriculum author for a SQLite-based tutor. "
    "Generate only the requested SQL concept, not a generic exercise. "
    "Keep the schema, description, setup_sql, and expected_query consistent. "
    "Reply with a single JSON object and nothing else."
)

_FORMAT_SPEC = """\
Use exactly this JSON shape:
{
  "exercise_id": "lowercase-id-with-hyphens",
  "title": "short title",
  "description": "the task for the learner; name any required output column aliases",
  "concept": "<the concept>",
  "difficulty": "<the difficulty>",
  "schema": [{"name": "table", "columns": [{"name": "col", "data_type": "INTEGER"}]}],
  "setup_sql": ["CREATE TABLE ...", "INSERT INTO ... VALUES (...)"],
  "expected_query": "SELECT ...;"
}
Rules: SQLite dialect; setup_sql contains only CREATE TABLE and INSERT INTO, one statement per string;
include 5 to 12 rows of realistic data; expected_query is one read-only SELECT that returns at least one row;
the expected_query must reference only tables and columns created by setup_sql;
the description must use the actual schema column names;
for window-function concepts, use SQLite-supported OVER, PARTITION BY, ORDER BY, and frame syntax;
for DDL/DML concepts, still provide a read-only learner task and a SELECT-based expected_query;
difficulty must be exactly one of: beginner, intermediate, advanced (lowercase)."""

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class ExerciseGenerationError(ValueError):
    """Raised when an LLM-generated exercise is invalid."""


class ExerciseGenerator:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_attempts: int = 1,
        verify: bool = False,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        self.provider = provider
        self.max_attempts = max_attempts
        self.verify = verify

    def generate(
        self,
        concept: str,
        difficulty: ExerciseDifficulty,
    ) -> Exercise:
        last_error: Exception | None = None
        feedback = ""

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._generate_once(concept, difficulty, feedback)
            except (ExerciseGenerationError, LLMProviderError) as error:
                last_error = error
                feedback = (
                    "\nYour previous answer was rejected: "
                    f"{error}\nFix that and reply with JSON only."
                )
                logger.warning(
                    "Exercise generation attempt %d/%d failed: %s",
                    attempt,
                    self.max_attempts,
                    error,
                )

        assert last_error is not None

        if isinstance(last_error, ExerciseGenerationError):
            raise last_error

        raise ExerciseGenerationError(str(last_error)) from last_error

    def _generate_once(
        self,
        concept: str,
        difficulty: ExerciseDifficulty,
        feedback: str,
    ) -> Exercise:
        request = LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            prompt=(
                f"Generate a {difficulty.value} SQL exercise "
                f"about {concept}.\n{_FORMAT_SPEC}{feedback}"
            ),
            json_mode=True,
            max_tokens=2048,
        )

        response = self.provider.generate(request)

        try:
            payload = json.loads(self._strip_fences(response.content))
            exercise = self._parse_exercise(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ExerciseGenerationError(
                f"Invalid generated exercise: {error}"
            ) from error

        validation = (
            verify_exercise(exercise)
            if self.verify
            else validate_exercise(exercise)
        )

        if not validation.is_valid:
            raise ExerciseGenerationError(
                "Exercise validation failed: "
                + "; ".join(validation.errors)
            )

        return exercise

    @staticmethod
    def _strip_fences(content: str) -> str:
        text = content.strip()
        match = _FENCE.match(text)
        return match.group(1) if match else text

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

        setup_sql = payload.get("setup_sql", ())

        if not isinstance(setup_sql, (list, tuple)) or not all(
            isinstance(s, str) for s in setup_sql
        ):
            raise ValueError("setup_sql must be a list of strings")

        return Exercise(
            exercise_id=payload["exercise_id"],
            title=payload["title"],
            description=payload["description"],
            concept=payload["concept"],
            difficulty=ExerciseDifficulty(str(payload["difficulty"]).strip().lower()),
            schema=schema,
            expected_query=payload["expected_query"],
            setup_sql=tuple(setup_sql),
        )
