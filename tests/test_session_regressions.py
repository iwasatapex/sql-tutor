"""Regression tests for the v2 + pre-v2 session integration."""
import json
from pathlib import Path

import pytest

from sql_tutor.catalog import load_exercises
from sql_tutor.cli import main
from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    TableColumn,
    TableSchema,
)
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.exercises.verifier import verify_exercise
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.session import (
    ExerciseSetupError,
    LearningSession,
    NoActiveExerciseError,
    NoExercisesAvailableError,
    SubmissionOutcome,
    _ignore_row_order,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BUNDLED = ExerciseRepository.from_directory(DATA_DIR).all()

USERS = TableSchema(
    "users",
    (TableColumn("id", "INTEGER"), TableColumn("name", "TEXT")),
)


def make_exercise(setup_sql: tuple[str, ...] = (), **overrides) -> Exercise:
    values = dict(
        exercise_id="users-names",
        title="User names",
        description="Return every user name.",
        concept="SELECT",
        difficulty=ExerciseDifficulty.BEGINNER,
        schema=(USERS,),
        expected_query="SELECT name FROM users;",
        setup_sql=setup_sql,
    )
    values.update(overrides)
    return Exercise(**values)


OWN_SETUP = (
    "CREATE TABLE users (id INTEGER, name TEXT)",
    "INSERT INTO users VALUES (1, 'Ann')",
)


@pytest.fixture
def store():
    instance = ProgressStore()
    yield instance
    instance.close()


def caller_engine() -> SQLEngine:
    engine = SQLEngine()
    engine.execute_setup([
        "CREATE TABLE users (id INTEGER, name TEXT)",
        "INSERT INTO users VALUES (1, 'Caller')",
    ])
    return engine


# --- every bundled exercise is self-contained -------------------------------

def test_bundled_data_includes_basic_catalog() -> None:
    ids = {e.exercise_id for e in BUNDLED}

    assert {"select-active-users", "order-users-by-name",
            "count-users-by-status"} <= ids


@pytest.mark.parametrize("exercise", BUNDLED, ids=lambda e: e.exercise_id)
def test_session_builds_database_before_reference_query_runs(
    exercise: Exercise,
    store: ProgressStore,
) -> None:
    repository = ExerciseRepository([exercise])
    session = LearningSession(
        repository,
        ExerciseSelector(Curriculum.default(), repository),
        store,
    )

    session.set_question_type(exercise.question_type.value)
    assert session.start().current_exercise == exercise

    if exercise.question_type.value == "predict":
        outcome = session.submit_prediction(session.expected_output())
    elif exercise.question_type.value == "explain":
        outcome = session.submit_explanation(exercise.reference_explanation)
    else:
        outcome = session.submit(exercise.expected_query)

    assert outcome.exercise_completed, outcome.feedback
    session.close()


def test_catalog_loader_returns_exercises_with_setup_sql() -> None:
    exercises = load_exercises(DATA_DIR / "exercises" / "basic.json")

    assert len(exercises) == 3

    for exercise in exercises:
        assert exercise.setup_sql, exercise.exercise_id
        assert verify_exercise(exercise).is_valid, exercise.exercise_id


def test_order_by_exercise_data_is_not_already_sorted() -> None:
    exercise = next(
        e for e in BUNDLED if e.exercise_id == "order-users-by-name"
    )
    engine = SQLEngine()
    engine.execute_setup(list(exercise.setup_sql))

    unsorted = engine.execute_query("SELECT name FROM users;").rows
    engine.close()

    assert unsorted != tuple(sorted(unsorted))


# --- pre-v2 API: start / state / next / submit ------------------------------

def test_start_returns_state_and_tracks_attempts(store: ProgressStore) -> None:
    exercise = make_exercise(OWN_SETUP)
    session = LearningSession((exercise,), SQLEngine(), store)

    assert session.state is None

    state = session.start()
    assert state.current_exercise == exercise
    assert state.attempts == 0
    assert state.last_feedback is None

    wrong = session.submit("SELECT id FROM users;")
    assert wrong.is_correct is False
    assert session.state.attempts == 1
    assert session.state.last_feedback == wrong.feedback

    right = session.submit("SELECT name FROM users;")
    assert right.is_correct is True
    assert session.state.attempts == 2
    session.close()


def test_next_moves_to_a_different_exercise(store: ProgressStore) -> None:
    first = make_exercise(OWN_SETUP)
    second = make_exercise(OWN_SETUP, exercise_id="users-ids",
                           expected_query="SELECT id FROM users;")
    session = LearningSession((first, second), SQLEngine(), store)

    a = session.start().current_exercise
    b = session.next().current_exercise

    assert a.exercise_id != b.exercise_id
    assert session.state.attempts == 0
    session.close()


def test_start_raises_when_no_exercise_is_available(
    store: ProgressStore,
) -> None:
    session = LearningSession((), SQLEngine(), store)

    with pytest.raises(NoExercisesAvailableError):
        session.start()

    with pytest.raises(ValueError):  # pre-v2 contract
        session.start()

    with pytest.raises(NoActiveExerciseError):
        session.submit("SELECT 1;")


def test_submit_outcome_reads_through_to_feedback(
    store: ProgressStore,
) -> None:
    session = LearningSession((make_exercise(OWN_SETUP),), SQLEngine(), store)
    session.start()

    outcome = session.submit("SELECT nope FROM users;")

    assert isinstance(outcome, SubmissionOutcome)
    assert outcome.error == outcome.feedback.error is not None
    assert outcome.message == outcome.feedback.message
    assert outcome.reason == outcome.feedback.reason
    assert outcome.hint is outcome.feedback.hint
    session.close()


def test_explicit_hint_level_is_recorded(store: ProgressStore) -> None:
    exercise = make_exercise(OWN_SETUP)
    session = LearningSession((exercise,), SQLEngine(), store)
    session.start()

    session.submit("SELECT id FROM users;", hint_level=2)

    attempts = store.get_attempts(exercise.exercise_id)
    assert attempts[-1].hint_level == 2
    session.close()


# --- database provisioning ---------------------------------------------------

def test_exercise_setup_is_isolated_from_the_callers_engine(
    store: ProgressStore,
) -> None:
    engine = caller_engine()
    session = LearningSession(
        (make_exercise(OWN_SETUP),), engine, store
    )
    session.start()

    assert session.submit("SELECT name FROM users;").is_correct
    session.close()

    # Caller's engine: untouched, still open, still holds its own data.
    assert engine.execute_query("SELECT name FROM users;").rows == (
        ("Caller",),
    )
    engine.close()


def test_callers_engine_is_used_for_exercises_without_setup_sql(
    store: ProgressStore,
) -> None:
    engine = caller_engine()
    session = LearningSession((make_exercise(),), engine, store)
    session.start()

    assert session.submit("SELECT name FROM users;").is_correct
    session.close()

    assert engine.execute_query("SELECT 1;").rows == ((1,),)  # not closed
    engine.close()


def test_missing_setup_sql_without_engine_fails_loudly(
    store: ProgressStore,
) -> None:
    repository = ExerciseRepository([make_exercise()])
    session = LearningSession(
        repository,
        ExerciseSelector(Curriculum.default(), repository),
        store,
    )

    with pytest.raises(ExerciseSetupError, match="users-names.*no setup_sql"):
        session.next_exercise()

    assert session.current is None
    with pytest.raises(NoActiveExerciseError):
        session.submit("SELECT name FROM users;")


def test_invalid_setup_sql_fails_loudly(store: ProgressStore) -> None:
    repository = ExerciseRepository(
        [make_exercise(("CREATE TABLE users (",))]
    )
    session = LearningSession(
        repository,
        ExerciseSelector(Curriculum.default(), repository),
        store,
    )

    with pytest.raises(ExerciseSetupError, match="users-names"):
        session.next_exercise()


def test_each_exercise_gets_a_fresh_database(store: ProgressStore) -> None:
    exercise = make_exercise(OWN_SETUP)
    other = make_exercise(OWN_SETUP, exercise_id="users-again")
    session = LearningSession((exercise, other), SQLEngine(), store)
    session.start()

    # Setup ran exactly once per exercise; re-running it would raise
    # "table users already exists" if the database were reused.
    assert session.submit("SELECT name FROM users;").is_correct
    assert session.next_exercise() is not None
    assert session.submit("SELECT name FROM users;").is_correct
    session.close()


def test_constructor_rejects_unsupported_arguments(
    store: ProgressStore,
) -> None:
    with pytest.raises(TypeError):
        LearningSession(object(), object(), store)  # type: ignore[arg-type]


# --- CLI surfaces setup problems cleanly ------------------------------------

def test_cli_reports_exercise_without_setup_sql(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "exercises").mkdir()
    (tmp_path / "exercises" / "bad.json").write_text(json.dumps([{
        "exercise_id": "no-data", "title": "t", "description": "d",
        "concept": "SELECT", "difficulty": "beginner",
        "schema": [{"name": "users", "columns": [
            {"name": "id", "data_type": "INTEGER"}]}],
        "expected_query": "SELECT id FROM users;",
    }]))

    code = main(
        ["--db", str(tmp_path / "p.db"), "--data-dir", str(tmp_path),
         "practice"],
        input_fn=lambda prompt: ":quit",
    )

    assert code == 1
    assert "no-data" in capsys.readouterr().err
