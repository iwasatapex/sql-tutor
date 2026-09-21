"""Regression tests for SQLite compatibility of generated exercises.

Covers the real failures reported against LLM-backed generation:
``no such function: ROW_COUNT`` (MySQL-ism in ``expected_query``), split
multi-row ``INSERT`` fragments rejected as
``Setup statements must be CREATE TABLE or INSERT INTO``, enum labels like
``Advanced``/``ADVANCED``, and prose-wrapped JSON replies.
"""

import json

from sql_tutor.exercises.generator import ExerciseGenerator
from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.exercises.sqlite_compat import (
    find_unsupported_functions,
    normalize_difficulty_label,
    normalize_setup_statements,
    sqlite_compatibility_errors,
)
from sql_tutor.exercises.validator import validate_exercise
from sql_tutor.llm.base import LLMProvider
from sql_tutor.llm.models import LLMRequest, LLMResponse


def payload(**overrides) -> dict:
    base = {
        "exercise_id": "students-above-90",
        "title": "High scorers",
        "description": "Return names of students scoring above 90.",
        "concept": "WHERE",
        "difficulty": "beginner",
        "schema": [{"name": "students", "columns": [
            {"name": "id", "data_type": "INTEGER"},
            {"name": "name", "data_type": "TEXT"},
            {"name": "score", "data_type": "REAL"},
        ]}],
        "setup_sql": [
            "CREATE TABLE students (id INTEGER, name TEXT, score REAL)",
            "INSERT INTO students VALUES (1, 'Alice', 88.5), "
            "(2, 'Bob', 95.0), (3, 'Cara', 97.5)",
        ],
        "expected_query": "SELECT name FROM students WHERE score > 90;",
    }
    base.update(overrides)
    return base


class ScriptedProvider(LLMProvider):
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self.replies.pop(0), model="scripted")


def generate(reply: str, **kwargs) -> object:
    return ExerciseGenerator(ScriptedProvider(reply), **kwargs).generate(
        "WHERE", ExerciseDifficulty.BEGINNER
    )


def test_row_count_in_expected_query_is_rejected_with_guidance() -> None:
    bad = payload(expected_query="SELECT name, ROW_COUNT() FROM students;")

    errors = validate_exercise(
        ExerciseGenerator._parse_exercise(json.loads(json.dumps(bad)))
    ).errors

    assert any("ROW_COUNT" in error for error in errors)
    assert any("changes()" in error for error in errors)


def test_row_count_is_rejected_before_verification() -> None:
    import pytest

    from sql_tutor.exercises.generator import ExerciseGenerationError

    bad = payload(expected_query="SELECT name, ROW_COUNT() FROM students;")

    with pytest.raises(ExerciseGenerationError, match="ROW_COUNT"):
        generate(json.dumps(bad))


def test_window_functions_are_accepted() -> None:
    ok = payload(
        expected_query=(
            "SELECT name, ROW_NUMBER() OVER (ORDER BY score DESC) AS rn "
            "FROM students;"
        )
    )

    assert validate_exercise(
        ExerciseGenerator._parse_exercise(ok)
    ).is_valid


def test_split_insert_fragments_are_reassembled() -> None:
    fragmented = payload(setup_sql=[
        "CREATE TABLE students (id INTEGER, name TEXT, score REAL)",
        "INSERT INTO students (id, name, score) VALUES",
        "(1, 'Alice', 88.5),",
        "(2, 'Bob', 95.0),",
        "(3, 'Cara', 97.5);",
    ])

    exercise = ExerciseGenerator._parse_exercise(fragmented)

    assert exercise.setup_sql == (
        "CREATE TABLE students (id INTEGER, name TEXT, score REAL)",
        "INSERT INTO students (id, name, score) VALUES "
        "(1, 'Alice', 88.5), (2, 'Bob', 95.0), (3, 'Cara', 97.5);",
    )
    assert validate_exercise(exercise).is_valid


def test_bare_row_tuples_are_still_rejected() -> None:
    import pytest

    from sql_tutor.exercises.generator import ExerciseGenerationError

    bad = payload(setup_sql=[
        "CREATE TABLE students (id INTEGER, name TEXT, score REAL)",
        "VALUES (1, 'Alice', 88.5), (2, 'Bob', 95.0);",
    ])

    with pytest.raises(
        ExerciseGenerationError, match="CREATE TABLE or INSERT"
    ):
        generate(json.dumps(bad))


def test_prose_wrapped_json_is_parsed() -> None:
    reply = (
        "Here is your exercise:\n"
        + json.dumps(payload())
        + "\nHope it helps!"
    )

    assert generate(reply).exercise_id == "students-above-90"


def test_enum_labels_are_normalized() -> None:
    assert normalize_difficulty_label("Advanced") == "advanced"
    assert normalize_difficulty_label("ADVANCED") == "advanced"
    assert normalize_difficulty_label(" advanced ") == "advanced"
    assert normalize_difficulty_label("nope") is None

    upper = payload(difficulty="ADVANCED")
    assert ExerciseGenerator._parse_exercise(upper).difficulty == (
        ExerciseDifficulty.ADVANCED
    )


def test_unsupported_function_scan() -> None:
    assert find_unsupported_functions("SELECT ROW_COUNT()") == ("ROW_COUNT",)
    assert find_unsupported_functions("select row_count()") == ("ROW_COUNT",)
    assert find_unsupported_functions("SELECT 'ROW_COUNT()'") == ()
    assert find_unsupported_functions(
        "SELECT ROW_NUMBER() OVER (ORDER BY score) FROM students;"
    ) == ()
    assert sqlite_compatibility_errors("SELECT NOW()")[0].startswith(
        "Unsupported function NOW()"
    )
    assert normalize_setup_statements("CREATE TABLE x (a INTEGER)") == (
        "CREATE TABLE x (a INTEGER)",
    )
    assert normalize_setup_statements({"x": 1}) is None


def test_setup_failure_names_statement_index_and_sql() -> None:
    from sql_tutor.exercises.verifier import verify_exercise

    bad = payload(setup_sql=[
        "CREATE TABLE students (id INTEGER, name TEXT)",
        "INSERT INTO TABLE students VALUES (1, 'Alice')",
    ])

    result = verify_exercise(
        ExerciseGenerator._parse_exercise(bad)
    )

    assert result.is_valid is False
    assert any(
        "statement 2 of 2" in error
        and "INSERT INTO TABLE students" in error
        and "TABLE" in error
        for error in result.errors
    ), result.errors


def test_expected_query_failure_shows_query_text() -> None:
    from sql_tutor.exercises.verifier import verify_exercise

    bad = payload(expected_query="SELECT * FROMM students;")

    result = verify_exercise(
        ExerciseGenerator._parse_exercise(bad)
    )

    assert result.is_valid is False
    assert any(
        "expected query failed" in error
        and "SELECT * FROMM students;" in error
        for error in result.errors
    ), result.errors


def test_malformed_setup_statement_shows_index_and_text() -> None:
    bad = ExerciseGenerator._parse_exercise(payload(setup_sql=[
        "CREATE TABLE students (id INTEGER)",
        "VALUES (1), (2);",
    ]))

    errors = validate_exercise(bad).errors

    assert any(
        "statement 2 of 2" in error and "VALUES (1), (2);" in error
        for error in errors
    ), errors
