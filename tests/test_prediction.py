"""Tests for Predict output grading (pipe-separated answer format)."""

from pathlib import Path

import pytest

from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.sql.engine import QueryResult
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.prediction import (
    COLUMN_SEPARATOR,
    format_query_result,
    prediction_matches,
)
from sql_tutor.tutor.session import LearningSession, NoActiveExerciseError

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_format_query_result_renders_header_and_rows() -> None:
    result = QueryResult(
        columns=("id", "name"),
        rows=((1, "Alice"), (2, None)),
    )

    assert format_query_result(result) == "id | name\n1 | Alice\n2 |"


def test_format_query_result_without_rows_is_header_only() -> None:
    result = QueryResult(columns=("count",), rows=())

    assert format_query_result(result) == "count"


def test_column_separator_matches_the_documented_format() -> None:
    assert COLUMN_SEPARATOR == " | "
    assert format_query_result(
        QueryResult(columns=("a", "b"), rows=((1, 2),))
    ).splitlines()[0] == "a | b"


def test_prediction_matches_ignores_blank_lines_and_padding() -> None:
    actual = "name | salary\nAlice | 100"

    assert prediction_matches("name | salary\nAlice | 100", actual)
    assert prediction_matches("name|salary\n  Alice|100  \n\n", actual)


def test_prediction_matches_rejects_wrong_values_and_shape() -> None:
    actual = "name | salary\nAlice | 100"

    assert not prediction_matches("name | salary\nAlice | 101", actual)
    assert not prediction_matches("name\nAlice", actual)
    assert not prediction_matches("", actual)
    # Row order matters: the reference query decides the order it returns.
    assert not prediction_matches(
        "name | salary\nBob | 50\nAlice | 100", actual
    )


@pytest.fixture
def session():
    repository = ExerciseRepository.from_directory(DATA_DIR)
    store = ProgressStore()
    instance = LearningSession(
        repository=repository,
        selector=ExerciseSelector(Curriculum.default(), repository),
        progress_store=store,
    )
    yield instance
    instance.close()
    store.close()


def test_submit_prediction_grades_a_correct_answer(session: LearningSession) -> None:
    session.set_question_type("predict")
    assert session.next_exercise() is not None
    exercise = session.current
    assert exercise is not None

    outcome = session.submit_prediction(session.expected_output())

    assert outcome.is_correct is True
    assert outcome.exercise_completed is True
    assert outcome.actual_output
    assert "Correct" in outcome.message


def test_submit_prediction_grades_a_wrong_answer(session: LearningSession) -> None:
    session.set_question_type("predict")
    assert session.next_exercise() is not None

    outcome = session.submit_prediction("nope | nope")

    assert outcome.is_correct is False
    assert outcome.exercise_completed is False
    assert outcome.failed_attempts == 1
    assert outcome.actual_output


def test_submit_prediction_records_the_attempt(session: LearningSession) -> None:
    session.set_question_type("predict")
    assert session.next_exercise() is not None
    exercise = session.current
    assert exercise is not None

    session.submit_prediction(session.expected_output())

    attempts = session.progress_store.get_attempts(exercise.exercise_id)
    assert len(attempts) == 1
    assert attempts[0].is_correct is True
    assert attempts[0].student_query == session.expected_output()


def test_submit_prediction_rejects_empty_answer(session: LearningSession) -> None:
    session.set_question_type("predict")
    assert session.next_exercise() is not None

    with pytest.raises(ValueError, match="cannot be empty"):
        session.submit_prediction("   ")


def test_expected_output_needs_an_active_exercise(session: LearningSession) -> None:
    with pytest.raises(NoActiveExerciseError):
        session.expected_output()
