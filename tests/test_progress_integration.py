from sql_tutor.exercises.models import (
    Exercise,
    ExerciseDifficulty,
    TableColumn,
    TableSchema,
)
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.orchestrator import TutorOrchestrator


def make_engine() -> SQLEngine:
    engine = SQLEngine()
    engine.execute_setup(
        [
            "CREATE TABLE users (id INTEGER, name TEXT, active INTEGER)",
            "INSERT INTO users VALUES (1, 'Alice', 1)",
        ]
    )
    return engine


def make_exercise() -> Exercise:
    return Exercise(
        exercise_id="select-users",
        title="Select users",
        description="Return active users.",
        concept="WHERE",
        difficulty=ExerciseDifficulty.BEGINNER,
        schema=(
            TableSchema(
                name="users",
                columns=(
                    TableColumn(name="id", data_type="INTEGER"),
                    TableColumn(name="name", data_type="TEXT"),
                    TableColumn(name="active", data_type="INTEGER"),
                ),
            ),
        ),
        expected_query="SELECT name FROM users WHERE active = 1;",
    )


def test_orchestrator_records_correct_attempt() -> None:
    engine = make_engine()
    store = ProgressStore()
    tutor = TutorOrchestrator(progress_store=store)

    feedback = tutor.submit_query(
        exercise=make_exercise(),
        engine=engine,
        student_query="SELECT name FROM users WHERE active = 1;",
    )

    attempts = store.get_attempts("select-users")

    assert feedback.is_correct is True
    assert len(attempts) == 1
    assert attempts[0].is_correct is True

    store.close()
    engine.close()


def test_orchestrator_records_invalid_attempt() -> None:
    engine = make_engine()
    store = ProgressStore()
    tutor = TutorOrchestrator(progress_store=store)

    feedback = tutor.submit_query(
        exercise=make_exercise(),
        engine=engine,
        student_query="DELETE FROM users;",
    )

    attempts = store.get_attempts("select-users")

    assert feedback.is_correct is False
    assert feedback.error is not None
    assert len(attempts) == 1
    assert attempts[0].is_correct is False

    store.close()
    engine.close()