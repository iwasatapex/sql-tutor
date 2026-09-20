from sql_tutor.catalog import load_exercises
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.session import LearningSession


def make_engine() -> SQLEngine:
    engine = SQLEngine()
    engine.execute_setup([
        "CREATE TABLE users (id INTEGER, name TEXT, active INTEGER)",
        "INSERT INTO users VALUES (1, 'Alice', 1)",
        "INSERT INTO users VALUES (2, 'Bob', 0)",
    ])
    return engine


def test_session_start_and_submit() -> None:
    exercises = load_exercises("data/exercises/basic.json")
    engine = make_engine()
    store = ProgressStore()
    session = LearningSession((exercises[0],), engine, store)

    state = session.start()
    assert state.current_exercise.exercise_id == "select-active-users"

    feedback = session.submit("SELECT name FROM users WHERE active = 1;")
    assert feedback.is_correct is True
    assert session.state is not None
    assert session.state.attempts == 1

    engine.close()
    store.close()
