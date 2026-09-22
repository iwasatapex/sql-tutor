import pytest

from sql_tutor.sql.engine import SQLEngine
from sql_tutor.sql.safety import (
    UnsafeQueryError,
    validate_read_only_query,
)


@pytest.fixture
def engine() -> SQLEngine:
    instance = SQLEngine()

    instance.execute_setup(
        [
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                active INTEGER
            )
            """,
            """
            INSERT INTO users (id, name, active)
            VALUES
                (1, 'Alice', 1),
                (2, 'Bob', 0),
                (3, 'Charlie', 1)
            """,
        ]
    )

    yield instance
    instance.close()


def test_select_query_returns_results(engine: SQLEngine) -> None:
    result = engine.execute_query(
        "SELECT id, name FROM users ORDER BY id;"
    )

    assert result.columns == ("id", "name")
    assert result.rows == (
        (1, "Alice"),
        (2, "Bob"),
        (3, "Charlie"),
    )


def test_filtered_query_returns_expected_rows(
    engine: SQLEngine,
) -> None:
    result = engine.execute_query(
        "SELECT name FROM users WHERE active = 1 ORDER BY id;"
    )

    assert result.rows == (
        ("Alice",),
        ("Charlie",),
    )


def test_write_query_is_rejected(engine: SQLEngine) -> None:
    with pytest.raises(UnsafeQueryError):
        engine.execute_query(
            "DELETE FROM users WHERE id = 1;"
        )


def test_query_can_run_from_another_thread(engine: SQLEngine) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            engine.execute_query,
            "SELECT id, name FROM users ORDER BY id;",
        )
        result = future.result()

    assert result.columns == ("id", "name")
    assert result.rows == ((1, "Alice"), (2, "Bob"), (3, "Charlie"))


def test_unterminated_quoted_segments_are_rejected() -> None:
    for query in (
        "SELECT 'unterminated",
        'SELECT "unterminated',
        "SELECT `unterminated",
        "SELECT [unterminated",
    ):
        with pytest.raises(UnsafeQueryError, match="unterminated"):
            validate_read_only_query(query)
