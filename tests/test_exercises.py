import pytest

from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    TableColumn,
    TableSchema,
)


def make_exercise() -> Exercise:
    return Exercise(
        exercise_id="select-users",
        title="Select Users",
        description="Retrieve all users.",
        concept="SELECT",
        difficulty=ExerciseDifficulty.BEGINNER,
        schema=(
            TableSchema(
                name="users",
                columns=(
                    TableColumn(name="id", data_type="INTEGER"),
                    TableColumn(name="name", data_type="TEXT"),
                ),
            ),
        ),
        expected_query="SELECT * FROM users;",
    )


def test_exercise_creation() -> None:
    exercise = make_exercise()

    assert exercise.exercise_id == "select-users"
    assert exercise.difficulty == ExerciseDifficulty.BEGINNER
    assert exercise.schema[0].name == "users"


def test_exercise_requires_schema() -> None:
    with pytest.raises(ValueError, match="at least one table"):
        Exercise(
            exercise_id="invalid",
            title="Invalid",
            description="Invalid exercise",
            concept="SELECT",
            difficulty=ExerciseDifficulty.BEGINNER,
            schema=(),
            expected_query="SELECT 1;",
        )


def test_exercise_requires_expected_query() -> None:
    with pytest.raises(ValueError, match="expected_query"):
        Exercise(
            exercise_id="invalid",
            title="Invalid",
            description="Invalid exercise",
            concept="SELECT",
            difficulty=ExerciseDifficulty.BEGINNER,
            schema=(
                TableSchema(
                    name="users",
                    columns=(
                        TableColumn(name="id", data_type="INTEGER"),
                    ),
                ),
            ),
            expected_query="",
        )
