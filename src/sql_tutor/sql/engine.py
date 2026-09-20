import sqlite3
from dataclasses import dataclass
from typing import Any

from sql_tutor.sql.safety import validate_read_only_query


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


class SQLEngine:
    def __init__(self) -> None:
        self._connection = sqlite3.connect(":memory:")

    def execute_setup(self, statements: list[str]) -> None:
        for statement in statements:
            self._connection.execute(statement)

        self._connection.commit()

    def execute_query(self, query: str) -> QueryResult:
        validate_read_only_query(query)

        cursor = self._connection.execute(query)

        columns = tuple(
            description[0]
            for description in cursor.description or ()
        )

        rows = tuple(tuple(row) for row in cursor.fetchall())

        return QueryResult(
            columns=columns,
            rows=rows,
        )

    def close(self) -> None:
        self._connection.close()
