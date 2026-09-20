import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from sql_tutor.sql.safety import validate_read_only_query


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


class SQLEngine:
    """In-memory SQLite engine.

    Setup statements may write; learner queries run with ``query_only`` on,
    a wall-clock timeout, and a row cap, on top of the keyword safety check.
    """

    def __init__(
        self,
        *,
        query_timeout_seconds: float = 2.0,
        max_rows: int = 10_000,
    ) -> None:
        self._connection = sqlite3.connect(":memory:")
        self._query_timeout_seconds = query_timeout_seconds
        self._max_rows = max_rows

    def execute_setup(self, statements: list[str]) -> None:
        self._connection.execute("PRAGMA query_only = OFF")

        for statement in statements:
            self._connection.execute(statement)

        self._connection.commit()

    def execute_query(self, query: str) -> QueryResult:
        validate_read_only_query(query)

        self._connection.execute("PRAGMA query_only = ON")

        deadline = time.monotonic() + self._query_timeout_seconds
        self._connection.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0,
            10_000,
        )

        try:
            cursor = self._connection.execute(query)

            columns = tuple(
                description[0]
                for description in cursor.description or ()
            )

            fetched = cursor.fetchmany(self._max_rows + 1)
        finally:
            self._connection.set_progress_handler(None, 0)

        if len(fetched) > self._max_rows:
            raise ValueError(
                f"Query returned more than {self._max_rows} rows"
            )

        return QueryResult(
            columns=columns,
            rows=tuple(tuple(row) for row in fetched),
        )

    def close(self) -> None:
        self._connection.close()
