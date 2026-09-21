from pathlib import Path

import pytest

from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.session import LearningSession, NoActiveExerciseError

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


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


def test_submit_without_exercise_raises(session: LearningSession) -> None:
    with pytest.raises(NoActiveExerciseError):
        session.submit("SELECT 1;")


def test_correct_answer_completes_and_is_recorded(
    session: LearningSession,
) -> None:
    exercise = session.next_exercise()
    assert exercise is not None

    outcome = session.submit(exercise.expected_query)

    assert outcome.exercise_completed
    attempts = session.progress_store.get_attempts(exercise.exercise_id)
    assert [a.is_correct for a in attempts] == [True]


def test_wrong_answers_escalate_to_automatic_hint(
    session: LearningSession,
) -> None:
    session.next_exercise()

    first = session.submit("SELECT id FROM employees;")
    second = session.submit("SELECT id FROM employees;")

    assert not first.exercise_completed
    assert first.feedback.hint is None
    assert second.feedback.hint is not None
    assert second.failed_attempts == 2


def test_requested_hints_escalate_and_are_recorded(
    session: LearningSession,
) -> None:
    exercise = session.next_exercise()
    assert exercise is not None

    assert session.request_hint().level == 1
    assert session.request_hint().level == 2

    session.submit("SELECT id FROM employees;")

    attempts = session.progress_store.get_attempts(exercise.exercise_id)
    assert attempts[-1].hint_level == 2


def test_broken_sql_reports_error_without_crashing(
    session: LearningSession,
) -> None:
    session.next_exercise()

    outcome = session.submit("SELECT nope FROM nowhere;")

    assert outcome.feedback.error is not None
    assert not outcome.exercise_completed
    assert session.preview("SELECT nope FROM nowhere;") is None


def test_write_queries_are_rejected(session: LearningSession) -> None:
    session.next_exercise()

    outcome = session.submit("DELETE FROM employees;")

    assert outcome.feedback.error is not None


def test_skip_moves_on_without_repeating(session: LearningSession) -> None:
    first = session.next_exercise()
    session.skip()
    second = session.next_exercise()

    assert first is not None and second is not None
    assert first.exercise_id != second.exercise_id


def test_unordered_exercises_accept_any_row_order(
    session: LearningSession,
) -> None:
    exercise = session.next_exercise()
    assert exercise is not None
    assert exercise.exercise_id == "select-01"

    outcome = session.submit("SELECT name FROM employees ORDER BY name DESC;")

    assert outcome.exercise_completed


def test_full_course_can_be_completed_by_reference_answers(
    session: LearningSession,
) -> None:
    completed = 0

    while (exercise := session.next_exercise()) is not None:
        assert session.submit(exercise.expected_query).exercise_completed
        completed += 1
        assert completed <= len(session.repository), "selector looped"

    # Curated topics are completed through the bundled catalog. Additional
    # curriculum topics are generation-first and have no static exercises.
    progress = session.topic_progress()
    catalog_progress = [item for item in progress if item.total_exercises > 0]
    assert all(item.is_complete for item in catalog_progress)
    assert completed >= 2 * len(catalog_progress)
