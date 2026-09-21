"""Session tests for difficulty and question-type selection."""

from pathlib import Path

import pytest

from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.session import LearningSession
from sql_tutor.tutor.session import QuestionTypeMismatchError

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


def test_difficulty_selection_pins_exact_match_when_available(
    session: LearningSession,
) -> None:
    session.set_topic("SELECT")
    session.set_difficulty("intermediate")
    exercise = session.next_exercise()

    assert exercise is not None
    assert exercise.concept.upper() == "SELECT"
    assert exercise.difficulty == ExerciseDifficulty.INTERMEDIATE


def test_difficulty_selection_falls_back_to_nearest_level(
    session: LearningSession,
) -> None:
    session.set_topic("SELECT")
    session.set_difficulty("advanced")
    exercise = session.next_exercise()

    assert exercise is not None
    assert exercise.concept.upper() == "SELECT"
    # SELECT has no advanced static exercise, so the nearest level wins
    # instead of failing with "No exercises available".
    assert exercise.difficulty == ExerciseDifficulty.INTERMEDIATE
    assert session.selected_difficulty == ExerciseDifficulty.ADVANCED


def test_difficulty_selection_accepts_enum_and_adaptive_reset(
    session: LearningSession,
) -> None:
    session.set_difficulty(ExerciseDifficulty.ADVANCED)
    assert session.selected_difficulty == ExerciseDifficulty.ADVANCED
    session.set_difficulty(None)
    assert session.selected_difficulty is None


def test_difficulty_selection_rejects_unknown_label(
    session: LearningSession,
) -> None:
    with pytest.raises(ValueError, match="Unknown difficulty"):
        session.set_difficulty("impossible")


def test_question_type_write_is_default_and_supported(
    session: LearningSession,
) -> None:
    assert session.selected_question_type == "write"
    session.set_question_type("write")
    assert session.selected_question_type == "write"


def test_question_type_rejects_unsupported_modes(
    session: LearningSession,
) -> None:
    with pytest.raises(ValueError, match="Unsupported question type"):
        session.set_question_type("translate")


def test_question_type_accepts_every_supported_mode(
    session: LearningSession,
) -> None:
    for question_type in ("write", "debug", "predict", "explain"):
        session.set_question_type(question_type)
        assert session.selected_question_type == question_type

    # Aliases and casing are accepted too.
    session.set_question_type("Explain SQL")
    assert session.selected_question_type == "explain"


def test_explain_mode_serves_an_exercise_and_grades_the_answer(
    session: LearningSession,
) -> None:
    session.set_question_type("explain")
    exercise = session.next_exercise()

    assert exercise is not None
    assert exercise.reference_explanation

    good = session.submit_explanation(exercise.reference_explanation)

    assert good.is_correct is True
    assert good.exercise_completed is True
    assert good.grade.is_gradable is True
    assert good.reference_explanation


def test_explain_mode_rejects_a_vague_answer(
    session: LearningSession,
) -> None:
    session.set_question_type("explain")
    assert session.next_exercise() is not None

    outcome = session.submit_explanation("It reads some rows.")

    assert outcome.is_correct is False
    assert outcome.exercise_completed is False
    assert outcome.failed_attempts == 1
    assert outcome.grade.missing


def test_explain_mode_records_the_attempt(
    session: LearningSession,
) -> None:
    session.set_question_type("explain")
    exercise = session.next_exercise()
    assert exercise is not None

    outcome = session.submit_explanation(exercise.reference_explanation)
    assert outcome.is_correct is True

    attempts = session.progress_store.get_attempts(exercise.exercise_id)
    assert [attempt.is_correct for attempt in attempts] == [True]


def test_explain_mode_rejects_an_empty_answer(
    session: LearningSession,
) -> None:
    session.set_question_type("explain")
    assert session.next_exercise() is not None

    with pytest.raises(ValueError, match="cannot be empty"):
        session.submit_explanation("   ")


def test_write_exercises_fall_back_to_their_description(
    session: LearningSession,
) -> None:
    """Any exercise can be explained via its description."""
    session.set_question_type("write")
    exercise = session.next_exercise()
    assert exercise is not None
    assert exercise.explanation == ""
    assert exercise.reference_explanation == exercise.description


def test_submission_methods_require_the_active_question_type(
    session: LearningSession,
) -> None:
    assert session.next_exercise() is not None
    with pytest.raises(QuestionTypeMismatchError, match="/api/predict"):
        session.submit_prediction("name")
    with pytest.raises(QuestionTypeMismatchError, match="/api/explain"):
        session.submit_explanation("It selects names.")

    session.set_question_type("predict")
    assert session.next_exercise() is not None
    with pytest.raises(QuestionTypeMismatchError, match="/api/submit"):
        session.submit("SELECT name FROM departments;")
