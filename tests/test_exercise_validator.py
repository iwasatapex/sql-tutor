from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    TableColumn,
    TableSchema,
)
from sql_tutor.exercises.validator import validate_exercise


def make_exercise(**overrides: object) -> Exercise:
    values = {
        "exercise_id": "select-users",
        "title": "Select Users",
        "description": "Retrieve users.",
        "concept": "SELECT",
        "difficulty": ExerciseDifficulty.BEGINNER,
        "schema": (
            TableSchema(
                name="users",
                columns=(
                    TableColumn(name="id", data_type="INTEGER"),
                    TableColumn(name="name", data_type="TEXT"),
                ),
            ),
        ),
        "expected_query": "SELECT * FROM users;",
    }

    values.update(overrides)
    return Exercise(**values)


def test_valid_exercise() -> None:
    result = validate_exercise(make_exercise())

    assert result.is_valid is True
    assert result.errors == ()


def test_invalid_table_name() -> None:
    exercise = make_exercise(
        schema=(
            TableSchema(
                name="invalid table",
                columns=(
                    TableColumn(name="id", data_type="INTEGER"),
                ),
            ),
        ),
    )

    result = validate_exercise(exercise)

    assert result.is_valid is False
    assert "Invalid table name: invalid table" in result.errors


def test_unsafe_expected_query() -> None:
    exercise = make_exercise(
        expected_query="DROP TABLE users;",
    )

    result = validate_exercise(exercise)

    assert result.is_valid is False
    assert any(
        error.startswith("Invalid expected query:")
        for error in result.errors
    )
