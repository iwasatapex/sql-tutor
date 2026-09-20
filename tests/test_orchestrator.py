from sql_tutor.exercises.models import Exercise, ExerciseDifficulty, TableColumn, TableSchema
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.tutor.orchestrator import TutorOrchestrator


def make_engine() -> SQLEngine:
    engine = SQLEngine()
    engine.execute_setup([
        "CREATE TABLE users (id INTEGER, name TEXT, active INTEGER)",
        "INSERT INTO users VALUES (1, 'Alice', 1)",
        "INSERT INTO users VALUES (2, 'Bob', 0)",
    ])
    return engine


def make_exercise() -> Exercise:
    return Exercise(
        exercise_id="select-active-users",
        title="Select active users",
        description="Return the names of active users.",
        concept="WHERE",
        difficulty=ExerciseDifficulty.BEGINNER,
        schema=(TableSchema(
            name="users",
            columns=(
                TableColumn(name="id", data_type="INTEGER"),
                TableColumn(name="name", data_type="TEXT"),
                TableColumn(name="active", data_type="INTEGER"),
            ),
        ),),
        expected_query="SELECT name FROM users WHERE active = 1;",
    )


def test_correct_query_returns_correct_feedback() -> None:
    engine = make_engine()
    feedback = TutorOrchestrator().submit_query(
        exercise=make_exercise(),
        engine=engine,
        student_query="SELECT name FROM users WHERE active = 1;",
    )
    assert feedback.is_correct is True
    assert feedback.error is None
    assert feedback.hint is None
    engine.close()


def test_incorrect_query_can_return_hint() -> None:
    engine = make_engine()
    feedback = TutorOrchestrator().submit_query(
        exercise=make_exercise(),
        engine=engine,
        student_query="SELECT name FROM users WHERE active = 0;",
        hint_level=1,
    )
    assert feedback.is_correct is False
    assert feedback.hint is not None
    assert feedback.hint.level == 1
    assert feedback.hint.message
    engine.close()


def test_correct_query_does_not_return_hint() -> None:
    engine = make_engine()
    feedback = TutorOrchestrator().submit_query(
        exercise=make_exercise(),
        engine=engine,
        student_query="SELECT name FROM users WHERE active = 1;",
        hint_level=1,
    )
    assert feedback.is_correct is True
    assert feedback.hint is None
    engine.close()


def test_unsafe_query_returns_feedback() -> None:
    engine = make_engine()
    feedback = TutorOrchestrator().submit_query(
        exercise=make_exercise(),
        engine=engine,
        student_query="DELETE FROM users;",
    )
    assert feedback.is_correct is False
    assert feedback.error is not None
    assert "Only SELECT" in feedback.error
    engine.close()


def test_invalid_sql_returns_feedback() -> None:
    engine = make_engine()
    feedback = TutorOrchestrator().submit_query(
        exercise=make_exercise(),
        engine=engine,
        student_query="SELECT missing_column FROM users;",
    )
    assert feedback.is_correct is False
    assert feedback.error is not None
    engine.close()
