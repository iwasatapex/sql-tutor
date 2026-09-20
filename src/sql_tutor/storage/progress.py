import sqlite3
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

from sql_tutor.learning.mastery import MasteryResult, MasteryTracker


@dataclass(frozen=True)
class Attempt:
    exercise_id: str
    student_query: str
    is_correct: bool
    hint_level: int | None = None
    created_at: str | None = None


class ProgressStore:
    def __init__(self, database_path: str = ":memory:") -> None:
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(str(database_path))
        self._connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exercise_id TEXT NOT NULL,
                student_query TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                hint_level INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def record_attempt(
        self,
        exercise_id: str,
        student_query: str,
        is_correct: bool,
        hint_level: int | None = None,
    ) -> Attempt:
        created_at = datetime.now(timezone.utc).isoformat()

        self._connection.execute(
            """
            INSERT INTO attempts (
                exercise_id,
                student_query,
                is_correct,
                hint_level,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                exercise_id,
                student_query,
                int(is_correct),
                hint_level,
                created_at,
            ),
        )
        self._connection.commit()

        return Attempt(
            exercise_id=exercise_id,
            student_query=student_query,
            is_correct=is_correct,
            hint_level=hint_level,
            created_at=created_at,
        )

    def get_attempts(self, exercise_id: str) -> tuple[Attempt, ...]:
        rows = self._connection.execute(
            """
            SELECT exercise_id, student_query, is_correct,
                   hint_level, created_at
            FROM attempts
            WHERE exercise_id = ?
            ORDER BY id
            """,
            (exercise_id,),
        ).fetchall()

        return tuple(
            Attempt(
                exercise_id=row["exercise_id"],
                student_query=row["student_query"],
                is_correct=bool(row["is_correct"]),
                hint_level=row["hint_level"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def get_all_attempts(self) -> tuple[Attempt, ...]:
        rows = self._connection.execute(
            """
            SELECT exercise_id, student_query, is_correct,
                   hint_level, created_at
            FROM attempts
            ORDER BY id
            """
        ).fetchall()

        return tuple(
            Attempt(
                exercise_id=row["exercise_id"],
                student_query=row["student_query"],
                is_correct=bool(row["is_correct"]),
                hint_level=row["hint_level"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def get_mastery(self, exercise_id: str) -> MasteryResult:
        attempts = self.get_attempts(exercise_id)
        results = tuple(attempt.is_correct for attempt in attempts)
        return MasteryTracker().calculate(results)

    def close(self) -> None:
        self._connection.close()