"""Session tests for difficulty and question-type selection."""

from pathlib import Path

import pytest

from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.session import LearningSession

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
        session.set_question_type("predict")
