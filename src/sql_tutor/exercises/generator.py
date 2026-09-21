import json
import logging
import re

from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    QuestionType,
    TableColumn,
    TableSchema,
)
from sql_tutor.exercises.sqlite_compat import (
    normalize_difficulty_label,
    normalize_question_type_label,
    normalize_setup_statements,
)
from sql_tutor.exercises.validator import validate_exercise
from sql_tutor.exercises.verifier import verify_exercise
from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.models import LLMRequest

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a rigorous SQL curriculum author for a SQLite-based tutor. "
    "Generate only the requested SQL concept, not a generic exercise. "
    "SQLite is the ONLY supported dialect: never use functions from MySQL, "
    "PostgreSQL, T-SQL, or Oracle (no ROW_COUNT(), NOW(), DATE_FORMAT(), "
    "NVL(), ROWNUM, DUAL, ...). Prefer portable SQL plus SQLite-supported "
    "features such as strftime(), window functions with OVER/PARTITION BY, "
    "and recursive CTEs. "
    "Keep the schema, description, setup_sql, expected_query, question_type, "
    "broken_query, and explanation consistent. "
    "For debug exercises, broken_query must be a genuinely buggy query that "
    "the expected_query fixes. "
    "For explain exercises, explanation must state what the expected_query "
    "returns and which clauses, tables and columns it uses. "
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
  "expected_query": "SELECT ...;",
  "question_type": "write",
  "broken_query": "",
  "explanation": ""
}
Rules: SQLite dialect ONLY (no ROW_COUNT(), NOW(), DATE_FORMAT(), or other
non-SQLite functions); setup_sql contains only CREATE TABLE and INSERT INTO,
one complete statement per string -- never split row tuples such as
"(1, 'Alice', 88.5)," into their own strings; a multi-row insert must be a
single string like "INSERT INTO students VALUES (1, 'Alice', 88.5),
(2, 'Bob', 95.0)"; include 5 to 12 rows of realistic data; expected_query is
one read-only SELECT that returns at least one row;
the expected_query must reference only tables and columns created by setup_sql;
the description must use the actual schema column names;
for window-function concepts, use SQLite-supported OVER, PARTITION BY,
ORDER BY, ROW_NUMBER/RANK/DENSE_RANK/LAG/LEAD, and ROWS/RANGE frame syntax;
for DDL/DML concepts, still provide a read-only learner task and a
SELECT-based expected_query;
difficulty must be exactly one of: beginner, intermediate, advanced
(lowercase);
question_type must be exactly one of: write, debug, predict, explain
(lowercase);
for debug exercises, broken_query is a non-empty SQL query that contains
a real bug (wrong column, wrong operator, missing WHERE, wrong JOIN, etc.)
that the learner must fix; the expected_query is the correct version;
for explain exercises, explanation is a non-empty natural-language answer
that names the tables, columns, filtering, grouping and ordering the
expected_query uses; learners are graded on how many of those ideas their
own explanation mentions, so be specific rather than vague;
for write, debug and predict exercises, explanation must be an empty
string; for write, predict and explain exercises, broken_query must be an
empty string."""

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_MAX_RESPONSE_CHARS = 100_000


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
        question_type: QuestionType | str = QuestionType.WRITE,
    ) -> Exercise:
        normalized_type = normalize_question_type_label(
            question_type.value if isinstance(question_type, QuestionType) else question_type
        )
        if normalized_type is None:
            raise ExerciseGenerationError(
                "question_type must be one of: write, debug, predict, explain"
            )
        requested_type = QuestionType(normalized_type)
        last_error: Exception | None = None
        feedback = ""

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._generate_once(
                    concept, difficulty, requested_type, feedback
                )
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
        question_type: QuestionType,
        feedback: str,
    ) -> Exercise:
        request = LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            prompt=(
                f"Generate a {difficulty.value} SQL exercise "
                f"about {concept}. The question_type must be exactly "
                f"'{question_type.value}'.\n{_FORMAT_SPEC}{feedback}"
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

        if exercise.question_type != question_type:
            raise ExerciseGenerationError(
                "Generated question_type "
                f"'{exercise.question_type.value}' does not match requested "
                f"'{question_type.value}'"
            )

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
        if match:
            return match.group(1)
        start = text.find("{")
        if start < 0:
            return text
        candidate = text[start : start + _MAX_RESPONSE_CHARS]
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(candidate):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return candidate[: index + 1]
        return text

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

        setup_sql = normalize_setup_statements(payload.get("setup_sql", ()))

        if setup_sql is None:
            raise ValueError("setup_sql must be a list of strings")

        normalized_difficulty = normalize_difficulty_label(
            payload.get("difficulty")
        )
        if normalized_difficulty is None:
            raise ValueError(
                "difficulty must be one of: beginner, intermediate, advanced"
            )

        return Exercise(
            exercise_id=payload["exercise_id"],
            title=payload["title"],
            description=payload["description"],
            concept=payload["concept"],
            difficulty=ExerciseDifficulty(normalized_difficulty),
            schema=schema,
            expected_query=payload["expected_query"],
            setup_sql=tuple(setup_sql),
            question_type=QuestionType(
                normalize_question_type_label(payload.get("question_type", "write"))
                or "write"
            ),
            broken_query=payload.get("broken_query", ""),
            explanation=payload.get("explanation", ""),
        )
