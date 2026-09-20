from sql_tutor.storage.progress import ProgressStore


def test_record_and_retrieve_attempt() -> None:
    store = ProgressStore()

    attempt = store.record_attempt(
        exercise_id="select-users",
        student_query="SELECT * FROM users;",
        is_correct=True,
        hint_level=1,
    )

    assert attempt.exercise_id == "select-users"
    assert attempt.is_correct is True
    assert attempt.hint_level == 1

    attempts = store.get_attempts("select-users")

    assert len(attempts) == 1
    assert attempts[0].student_query == "SELECT * FROM users;"

    store.close()


def test_attempts_are_filtered_by_exercise() -> None:
    store = ProgressStore()

    store.record_attempt("exercise-a", "SELECT 1;", True)
    store.record_attempt("exercise-b", "SELECT 2;", False)

    attempts = store.get_attempts("exercise-a")

    assert len(attempts) == 1
    assert attempts[0].exercise_id == "exercise-a"

    store.close()

from sql_tutor.learning.mastery import MasteryLevel


def test_get_mastery_for_exercise() -> None:
    store = ProgressStore()

    store.record_attempt('select-users', 'SELECT 1;', True)
    store.record_attempt('select-users', 'SELECT 2;', True)
    store.record_attempt('select-users', 'SELECT 3;', False)
    store.record_attempt('select-users', 'SELECT 4;', True)

    mastery = store.get_mastery('select-users')

    assert mastery.level == MasteryLevel.PROFICIENT
    assert mastery.accuracy == 0.75

    store.close()


def test_get_mastery_for_new_exercise() -> None:
    store = ProgressStore()

    mastery = store.get_mastery('new-exercise')

    assert mastery.level == MasteryLevel.NOVICE
    assert mastery.accuracy == 0.0

    store.close()

