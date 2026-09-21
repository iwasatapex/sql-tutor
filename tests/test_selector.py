from pathlib import Path

import pytest

from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    QuestionType,
    TableColumn,
    TableSchema,
)
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.storage.progress import Attempt

B = ExerciseDifficulty.BEGINNER
I = ExerciseDifficulty.INTERMEDIATE
A = ExerciseDifficulty.ADVANCED


def make(
    exercise_id: str,
    concept: str,
    difficulty: ExerciseDifficulty,
    question_type: QuestionType = QuestionType.WRITE,
) -> Exercise:
    return Exercise(
        exercise_id=exercise_id,
        title=exercise_id,
        description="d",
        concept=concept,
        difficulty=difficulty,
        schema=(TableSchema("t", (TableColumn("id", "INTEGER"),)),),
        expected_query="SELECT id FROM t;",
        question_type=question_type,
    )


def attempt(exercise_id: str, ok: bool) -> Attempt:
    return Attempt(exercise_id=exercise_id, student_query="q", is_correct=ok)


@pytest.fixture
def selector() -> ExerciseSelector:
    repository = ExerciseRepository([
        make("s1", "SELECT", B),
        make("s2", "SELECT", B),
        make("s3", "SELECT", I),
        make("w1", "WHERE", B),
        make("w2", "WHERE", B),
    ])
    return ExerciseSelector(Curriculum.default(), repository)


def test_new_learner_starts_at_first_topic(selector: ExerciseSelector) -> None:
    exercise = selector.select_next([])

    assert exercise is not None
    assert exercise.concept == "SELECT"
    assert exercise.difficulty == B


def test_solved_exercises_are_not_repeated(selector: ExerciseSelector) -> None:
    exercise = selector.select_next([attempt("s1", True)])

    assert exercise is not None
    assert exercise.exercise_id != "s1"


def test_advances_to_next_topic_when_proficient(
    selector: ExerciseSelector,
) -> None:
    exercise = selector.select_next([attempt("s1", True), attempt("s2", True)])

    assert exercise is not None
    assert exercise.concept == "WHERE"


def test_stays_on_topic_when_struggling(selector: ExerciseSelector) -> None:
    attempts = [attempt("s1", False), attempt("s1", False), attempt("s1", True),
                attempt("s2", True)]

    exercise = selector.select_next(attempts)

    # Two solved, but recent accuracy is 50%: not proficient yet.
    assert exercise is not None
    assert exercise.exercise_id == "s3"


def test_topic_with_everything_solved_is_complete(
    selector: ExerciseSelector,
) -> None:
    attempts = [attempt("s1", False), attempt("s1", False), attempt("s1", True),
                attempt("s2", False), attempt("s2", True), attempt("s3", True)]

    exercise = selector.select_next(attempts)

    assert exercise is not None
    assert exercise.concept == "WHERE"


def test_difficulty_rises_after_three_correct_in_a_row(
    selector: ExerciseSelector,
) -> None:
    attempts = [attempt("s1", True), attempt("s1", True), attempt("s1", True)]
    # s1 solved; success streak pushes the target to INTERMEDIATE.
    exercise = selector.select_next(attempts)

    assert exercise is not None
    assert exercise.exercise_id == "s3"


def test_skipped_exercises_are_excluded(selector: ExerciseSelector) -> None:
    exercise = selector.select_next([], exclude_ids={"s1"})

    assert exercise is not None
    assert exercise.exercise_id == "s2"


def test_returns_none_when_everything_is_done(
    selector: ExerciseSelector,
) -> None:
    attempts = [attempt(i, True) for i in ("s1", "s2", "s3", "w1", "w2")]

    assert selector.select_next(attempts) is None


def test_explicit_difficulty_prefers_matching_exercises(
    selector: ExerciseSelector,
) -> None:
    exercise = selector.select_next([], difficulty=I)

    assert exercise is not None
    assert exercise.difficulty == I
    assert exercise.exercise_id == "s3"


def test_explicit_difficulty_falls_back_to_nearest_level(
    selector: ExerciseSelector,
) -> None:
    exercise = selector.select_next([], concept="WHERE", difficulty=A)

    assert exercise is not None
    assert exercise.concept == "WHERE"
    assert exercise.difficulty == B


def test_requested_question_type_never_falls_back(selector: ExerciseSelector) -> None:
    assert selector.select_next([], question_type="predict") is None


def test_requested_question_type_selects_matching_exercise() -> None:
    repository = ExerciseRepository([
        make("write", "SELECT", B),
        make("predict", "SELECT", B, QuestionType.PREDICT),
    ])
    selector = ExerciseSelector(Curriculum.default(), repository)

    exercise = selector.select_next([], question_type="predict")

    assert exercise is not None
    assert exercise.question_type == QuestionType.PREDICT



def test_unknown_exercise_ids_in_history_are_ignored(
    selector: ExerciseSelector,
) -> None:
    exercise = selector.select_next([attempt("deleted-exercise", True)])

    assert exercise is not None
    assert exercise.concept == "SELECT"


def test_topic_progress_reports_counts(selector: ExerciseSelector) -> None:
    progress = selector.topic_progress(
        [attempt("s1", True), attempt("s2", False)]
    )

    select = progress[0]
    assert select.solved == 1
    assert select.attempts == 2
    assert select.total_exercises == 3
    assert not select.is_complete
