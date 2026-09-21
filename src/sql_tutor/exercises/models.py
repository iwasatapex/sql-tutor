from dataclasses import dataclass
from enum import StrEnum

from sql_tutor.exercises.sqlite_compat import normalize_question_type_label


class ExerciseDifficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class QuestionType(StrEnum):
    WRITE = "write"
    DEBUG = "debug"
    PREDICT = "predict"
    EXPLAIN = "explain"


@dataclass(frozen=True)
class TableColumn:
    name: str
    data_type: str


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[TableColumn, ...]


@dataclass(frozen=True)
class Exercise:
    exercise_id: str
    title: str
    description: str
    concept: str
    difficulty: ExerciseDifficulty
    schema: tuple[TableSchema, ...]
    expected_query: str
    setup_sql: tuple[str, ...] = ()
    question_type: QuestionType = QuestionType.WRITE
    broken_query: str = ""
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.exercise_id.strip():
            raise ValueError("exercise_id cannot be empty")

        if not self.title.strip():
            raise ValueError("title cannot be empty")

        if not self.description.strip():
            raise ValueError("description cannot be empty")

        if not self.concept.strip():
            raise ValueError("concept cannot be empty")

        if not self.schema:
            raise ValueError("exercise must contain at least one table")

        if not self.expected_query.strip():
            raise ValueError("expected_query cannot be empty")

        if normalize_question_type_label(self.question_type.value) is None:
            raise ValueError(
                f"Unknown question_type: {self.question_type!r}. "
                "Use write, debug, predict, or explain."
            )

        if self.question_type == QuestionType.DEBUG and not self.broken_query.strip():
            raise ValueError(
                "Debug exercises must include a non-empty broken_query"
            )

        if self.question_type == QuestionType.EXPLAIN and not self.explanation.strip():
            raise ValueError(
                "Explain exercises must include a non-empty explanation"
            )

    @property
    def reference_explanation(self) -> str:
        """Model answer used to grade an Explain SQL answer.

        Authored exercises can provide a dedicated ``explanation``. Any
        other exercise falls back to its ``description``, which already
        states in prose what the reference query returns.
        """
        return self.explanation.strip() or self.description.strip()
