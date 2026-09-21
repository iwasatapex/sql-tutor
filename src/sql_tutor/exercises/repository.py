import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    QuestionType,
    TableColumn,
    TableSchema,
)
from sql_tutor.exercises import sqlite_compat


class ExerciseLoadError(ValueError):
    """Raised when exercise or dataset files are malformed."""


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "1" if value else "0"

    if isinstance(value, (int, float)):
        return repr(value)

    return "'" + str(value).replace("'", "''") + "'"


def _parse_table(table: dict[str, Any]) -> TableSchema:
    return TableSchema(
        name=table["name"],
        columns=tuple(
            TableColumn(name=c["name"], data_type=c["data_type"])
            for c in table["columns"]
        ),
    )


def _setup_statements(tables: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    statements: list[str] = []

    for table in tables:
        columns = ", ".join(
            f"{c['name']} {c['data_type']}" for c in table["columns"]
        )
        statements.append(f"CREATE TABLE {table['name']} ({columns})")

        for row in table.get("rows", []):
            values = ", ".join(_sql_literal(v) for v in row)
            statements.append(
                f"INSERT INTO {table['name']} VALUES ({values})"
            )

    return tuple(statements)


class ExerciseRepository:
    def __init__(self, exercises: Iterable[Exercise] = ()) -> None:
        self._exercises: dict[str, Exercise] = {}

        for exercise in exercises:
            self.add(exercise)

    def add(self, exercise: Exercise) -> None:
        if exercise.exercise_id in self._exercises:
            raise ExerciseLoadError(
                f"Duplicate exercise_id: {exercise.exercise_id}"
            )

        self._exercises[exercise.exercise_id] = exercise

    def get(self, exercise_id: str) -> Exercise | None:
        return self._exercises.get(exercise_id)

    def all(self) -> tuple[Exercise, ...]:
        return tuple(self._exercises.values())

    def for_concept(self, concept: str) -> tuple[Exercise, ...]:
        wanted = concept.strip().upper()

        return tuple(
            e for e in self._exercises.values()
            if e.concept.upper() == wanted
        )

    def __len__(self) -> int:
        return len(self._exercises)

    @classmethod
    def from_directory(cls, data_dir: Path) -> "ExerciseRepository":
        """Load ``datasets/*.json`` and ``exercises/**/*.json``.

        An exercise either references a dataset by name (optionally listing
        the ``tables`` to show) or carries its own ``schema`` and
        ``setup_sql`` inline.
        """
        datasets: dict[str, dict[str, Any]] = {}
        dataset_dir = data_dir / "datasets"

        if dataset_dir.is_dir():
            for path in sorted(dataset_dir.glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                datasets[payload["name"]] = payload

        repository = cls()
        exercise_dir = data_dir / "exercises"

        if not exercise_dir.is_dir():
            return repository

        for path in sorted(exercise_dir.rglob("*.json")):
            try:
                payloads = json.loads(path.read_text(encoding="utf-8"))

                for payload in payloads:
                    repository.add(cls._build(payload, datasets))
            except (KeyError, TypeError, ValueError) as error:
                raise ExerciseLoadError(
                    f"{path.name}: {error!r}"
                ) from error

        return repository

    @staticmethod
    def _build(
        payload: dict[str, Any],
        datasets: dict[str, dict[str, Any]],
    ) -> Exercise:
        if "dataset" in payload:
            dataset = datasets[payload["dataset"]]
            tables = dataset["tables"]
            shown = payload.get("tables")

            schema = tuple(
                _parse_table(t) for t in tables
                if shown is None or t["name"] in shown
            )
            setup_sql = _setup_statements(tables)
        else:
            schema = tuple(_parse_table(t) for t in payload["schema"])
            setup_sql = tuple(payload.get("setup_sql", ()))

        return Exercise(
            exercise_id=payload["exercise_id"],
            title=payload["title"],
            description=payload["description"],
            concept=payload["concept"],
            difficulty=ExerciseDifficulty(payload["difficulty"]),
            schema=schema,
            expected_query=payload["expected_query"],
            setup_sql=setup_sql,
            question_type=QuestionType(
                sqlite_compat.normalize_question_type_label(
                    payload.get("question_type", "write")
                )
                or "write"
            ),
            broken_query=payload.get("broken_query", ""),
        )


def exercise_to_payload(exercise: Exercise) -> dict[str, Any]:
    """Serialize an exercise to the inline JSON form the loader reads."""
    return {
        "exercise_id": exercise.exercise_id,
        "title": exercise.title,
        "description": exercise.description,
        "concept": exercise.concept,
        "difficulty": exercise.difficulty.value,
        "schema": [
            {
                "name": table.name,
                "columns": [
                    {"name": c.name, "data_type": c.data_type}
                    for c in table.columns
                ],
            }
            for table in exercise.schema
        ],
        "setup_sql": list(exercise.setup_sql),
        "expected_query": exercise.expected_query,
        "question_type": exercise.question_type.value,
        "broken_query": exercise.broken_query,
    }
