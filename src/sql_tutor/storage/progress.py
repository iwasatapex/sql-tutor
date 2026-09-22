from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sql_tutor.learning.mastery import MasteryResult, MasteryTracker


@dataclass(frozen=True)
class Attempt:
    exercise_id: str
    student_query: str
    is_correct: bool
    hint_level: int | None = None
    created_at: str | None = None


class ProgressStore:
    """SQLite-backed progress store safe for ThreadingHTTPServer.

    File-backed databases use a fresh connection per operation. In-memory
    databases retain one connection because each SQLite in-memory connection
    is a separate database; access is serialized with a re-entrant lock.
    """

    def __init__(self, database_path: str = ":memory:") -> None:
        self._database_path = database_path
        self._memory = database_path == ":memory:"
        self._lock = threading.RLock()
        self._closed = False

        if not self._memory:
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
            self._configure_file_database()
            self._connection: sqlite3.Connection | None = None
        else:
            self._connection = self._connect()

        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=30.0,
            isolation_level="DEFERRED",
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _configure_file_database(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 30000")

    def _connections(self) -> Iterator[sqlite3.Connection]:
        if self._memory:
            assert self._connection is not None
            yield self._connection
        else:
            connection = self._connect()
            try:
                yield connection
            finally:
                connection.close()

    def _create_tables(self) -> None:
        with self._lock:
            for connection in self._connections():
                connection.execute(
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
                connection.commit()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("ProgressStore is closed")

    def record_attempt(
        self,
        exercise_id: str,
        student_query: str,
        is_correct: bool,
        hint_level: int | None = None,
    ) -> Attempt:
        self._ensure_open()
        created_at = datetime.now(UTC).isoformat()
        with self._lock:
            for connection in self._connections():
                connection.execute(
                    """
                    INSERT INTO attempts (
                        exercise_id, student_query, is_correct,
                        hint_level, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """ ,
                    (exercise_id, student_query, int(is_correct), hint_level, created_at),
                )
                connection.commit()

        return Attempt(exercise_id, student_query, is_correct, hint_level, created_at)

    @staticmethod
    def _to_attempt(row: sqlite3.Row) -> Attempt:
        return Attempt(
            exercise_id=row["exercise_id"],
            student_query=row["student_query"],
            is_correct=bool(row["is_correct"]),
            hint_level=row["hint_level"],
            created_at=row["created_at"],
        )

    def _fetch_attempts(self, query: str, parameters: tuple[object, ...] = ()) -> tuple[Attempt, ...]:
        self._ensure_open()
        with self._lock:
            for connection in self._connections():
                rows = connection.execute(query, parameters).fetchall()
                return tuple(self._to_attempt(row) for row in rows)
        return ()

    def get_attempts(self, exercise_id: str) -> tuple[Attempt, ...]:
        return self._fetch_attempts(
            """
            SELECT exercise_id, student_query, is_correct, hint_level, created_at
            FROM attempts WHERE exercise_id = ? ORDER BY id
            """,
            (exercise_id,),
        )

    def get_all_attempts(self) -> tuple[Attempt, ...]:
        return self._fetch_attempts(
            """
            SELECT exercise_id, student_query, is_correct, hint_level, created_at
            FROM attempts ORDER BY id
            """
        )

    def get_mastery(self, exercise_id: str) -> MasteryResult:
        results = tuple(attempt.is_correct for attempt in self.get_attempts(exercise_id))
        return MasteryTracker().calculate(results)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._memory and self._connection is not None:
                self._connection.close()
                self._connection = None
            self._closed = True
