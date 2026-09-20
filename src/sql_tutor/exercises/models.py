from dataclasses import dataclass
from enum import StrEnum


class ExerciseDifficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


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
