import os
import re
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from sql_tutor.sql.safety import UnsafeQueryError, validate_read_only_query


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


class SQLEngine:
    """SQLite engine with one connection per operation.

    The database is backed by a private temporary file so setup data is
    available to connections created by other request threads. Every
    operation opens and closes its own SQLite connection, preserving
    SQLite's default same-thread safety without using check_same_thread=False.
    """

    def __init__(
        self,
        *,
        query_timeout_seconds: float = 2.0,
        max_rows: int = 10_000,
        max_value_bytes: int = 1_000_000,
        max_result_bytes: int = 10_000_000,
    ) -> None:
        fd, path = tempfile.mkstemp(prefix="sql-tutor-", suffix=".sqlite3")
        os.close(fd)
        self._db_path = Path(path)
        self._query_timeout_seconds = query_timeout_seconds
        self._max_rows = max_rows
        self._max_value_bytes = max_value_bytes
        self._max_result_bytes = max_result_bytes
        self._lifecycle_lock = Lock()
        self._closed = False

    def _connect(self) -> sqlite3.Connection:
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("SQL engine is closed")
            connection = sqlite3.connect(str(self._db_path), timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def execute_setup(self, statements: list[str]) -> None:
        connection = self._connect()
        total = len(statements)
        try:
            connection.execute("PRAGMA query_only = OFF")
            for index, statement in enumerate(statements, start=1):
                stripped = statement.strip()
                if not stripped:
                    continue
                head = re.match(
                    r"(CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?|INSERT\s+INTO)\b",
                    stripped,
                    re.IGNORECASE,
                )
                if head is None:
                    raise UnsafeQueryError(
                        "Setup statements must be CREATE TABLE or INSERT INTO "
                        f"(statement {index} of {total}): {stripped}"
                    )
                try:
                    connection.execute(statement)
                except sqlite3.Error as error:
                    raise sqlite3.OperationalError(
                        f"Failed to execute setup_sql statement {index} "
                        f"of {total}: {stripped}: {error}"
                    ) from error
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _value_size(value: object) -> int:
        if value is None:
            return 0
        if isinstance(value, (bytes, bytearray, memoryview)):
            return len(bytes(value))
        if isinstance(value, str):
            return len(value.encode("utf-8"))
        return len(str(value).encode("utf-8"))

    def execute_query(self, query: str) -> QueryResult:
        validate_read_only_query(query)
        connection = self._connect()
        try:
            connection.execute("PRAGMA query_only = ON")

            deadline = time.monotonic() + self._query_timeout_seconds
            connection.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0,
                10_000,
            )

            try:
                cursor = connection.execute(query)
                columns = tuple(
                    description[0]
                    for description in cursor.description or ()
                )
                fetched = cursor.fetchmany(self._max_rows + 1)
            finally:
                connection.set_progress_handler(None, 0)

            if len(fetched) > self._max_rows:
                raise ValueError(
                    f"Query returned more than {self._max_rows} rows"
                )

            normalized_rows: list[tuple[object, ...]] = []
            total_size = 0
            for row in fetched:
                converted = tuple(row)
                row_size = 0
                for value in converted:
                    value_size = self._value_size(value)
                    if value_size > self._max_value_bytes:
                        raise ValueError(
                            "Query result contains a value larger than "
                            f"{self._max_value_bytes} bytes"
                        )
                    row_size += value_size
                total_size += row_size
                if total_size > self._max_result_bytes:
                    raise ValueError(
                        "Query result exceeds the configured size limit of "
                        f"{self._max_result_bytes} bytes"
                    )
                normalized_rows.append(converted)

            return QueryResult(
                columns=columns,
                rows=tuple(normalized_rows),
            )
        finally:
            connection.close()

    def close(self) -> None:
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._db_path.unlink(missing_ok=True)
            except OSError:
                pass
