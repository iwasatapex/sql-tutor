"""Backend tests for web endpoints and session state transitions."""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from sql_tutor.config import Settings
from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.tutor.session import NoExercisesAvailableError
from sql_tutor.web import EmptySubmissionError, TutorWebApp


def make_app(tmp_path: Path) -> TutorWebApp:
    settings = Settings(
        data_dir=Path("data"), database_path=tmp_path / "progress.db"
    )
    return TutorWebApp(settings)


def test_initial_state_loads_with_exercise(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        state = app.state()
        assert state["available"] is True
        assert state["exercise"]["id"]
        assert state["exercise"]["schema"]
        assert state["topics"]
        assert state["selected_topic"] is None
        assert state["selected_difficulty"] == "adaptive"
        assert state["question_type"] == "write"
    finally:
        app.close()


def test_topic_selection_changes_exercise(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        selected = app.choose_topic("WHERE")
        assert selected["selected_topic"] == "WHERE"
        assert selected["exercise"]["concept"].upper() == "WHERE"
        adaptive = app.choose_topic(None)
        assert adaptive["selected_topic"] is None
    finally:
        app.close()


def test_invalid_topic_returns_clear_error(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with pytest.raises(ValueError, match="Unknown curriculum topic"):
            app.choose_topic("NOT A TOPIC")
    finally:
        app.close()


def test_difficulty_selection_pins_exercise_level(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        app.choose_topic("SELECT")
        selected = app.choose_difficulty("intermediate")
        assert selected["selected_difficulty"] == "intermediate"
        assert (
            selected["exercise"]["difficulty"]
            == ExerciseDifficulty.INTERMEDIATE.value
        )
        # A level with no exact static match falls back to nearest.
        nearest = app.choose_difficulty("advanced")
        assert nearest["selected_difficulty"] == "advanced"
        assert nearest["exercise"]["concept"].upper() == "SELECT"
        adaptive = app.choose_difficulty("adaptive")
        assert adaptive["selected_difficulty"] == "adaptive"
    finally:
        app.close()


def test_invalid_difficulty_returns_clear_error(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with pytest.raises(ValueError, match="Unknown difficulty"):
            app.choose_difficulty("impossible")
    finally:
        app.close()


def test_question_type_write_is_accepted(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        payload = app.choose_question_type("write")
        assert payload["question_type"] == "write"
    finally:
        app.close()


def test_unsupported_question_type_is_rejected(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with pytest.raises(ValueError, match="Unsupported question type"):
            app.choose_question_type("explain")
    finally:
        app.close()


def test_correct_submission_records_progress(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        exercise_id = app.state()["exercise"]["id"]
        expected = app.session.current.expected_query
        result = app.submit(expected)
        assert result["feedback"]["is_correct"] is True
        attempts = app.session.progress_store.get_attempts(exercise_id)
        assert [a.is_correct for a in attempts] == [True]
        progress = app.progress()
        assert progress["items"]
    finally:
        app.close()


def test_incorrect_submission_keeps_exercise(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        before = app.state()["exercise"]["id"]
        result = app.submit("SELECT id FROM employees;")
        assert result["feedback"]["is_correct"] is False
        assert result["exercise"]["id"] == before
        assert result["attempts"] == 1
    finally:
        app.close()


def test_empty_submission_is_rejected_without_side_effects(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    try:
        with pytest.raises(EmptySubmissionError, match="cannot be empty"):
            app.submit("   ")
        assert app.session.progress_store.get_all_attempts() == ()
    finally:
        app.close()


def test_invalid_sql_returns_feedback_not_exception(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path)
    try:
        result = app.submit("DROP TABLE employees;")
        assert result["feedback"]["is_correct"] is False
        assert result["feedback"]["error"]
    finally:
        app.close()


def test_hint_request_returns_hint(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        result = app.hint()
        assert result["hint"]
        assert result["hints_used"] == 1
    finally:
        app.close()


def test_skip_advances_and_next_skips_current(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        first = app.state()["exercise"]["id"]
        skipped = app.skip()
        assert skipped["exercise"]["id"] != first
        second = skipped["exercise"]["id"]
        advanced = app.next()
        assert advanced["exercise"]["id"] not in {first, second}
    finally:
        app.close()


def _make_predict_exercise(app: TutorWebApp) -> None:
    """Configure the app to serve a predict-type exercise."""
    app.session.set_question_type("predict")
    app.session.next()


def test_predict_correct_prediction(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        _make_predict_exercise(app)
        exercise_id = app.session.current.exercise_id

        response = app.predict(app.session.expected_output())
        assert response["feedback"]["is_correct"] is True
        assert response["feedback"]["message"] == (
            "Correct! Your prediction matched the query output."
        )
        # Predict answers count like any other attempt so progress advances.
        attempts = app.session.progress_store.get_attempts(exercise_id)
        assert [attempt.is_correct for attempt in attempts] == [True]
    finally:
        app.close()


def test_predict_incorrect_prediction(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        _make_predict_exercise(app)
        exercise_id = app.session.current.exercise_id
        response = app.predict("wrong | data\n1 | 2")
        assert response["feedback"]["is_correct"] is False
        assert "actual_output" in response
        assert response["actual_output"]
        assert response["failed_attempts"] == 1

        attempts = app.session.progress_store.get_attempts(exercise_id)
        assert [attempt.is_correct for attempt in attempts] == [False]
    finally:
        app.close()


def test_predict_empty_prediction_rejected(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        _make_predict_exercise(app)
        with pytest.raises(EmptySubmissionError, match="cannot be empty"):
            app.predict("   ")
    finally:
        app.close()


def test_no_exercises_state_is_explicit(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        app.session.repository._exercises.clear()
        app.session._skipped.clear()
        app.session._close_engine()
        app.session.current = None
        state = app.state()
        assert state["available"] is False
        assert state["exercise"] is None
        assert "No exercises available" in (
            state.get("message") or state.get("error") or ""
        )
        with pytest.raises(NoExercisesAvailableError):
            app.next()
    finally:
        app.close()


def test_generate_applies_topic_and_difficulty(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        payload = app.generate("SELECT", "beginner", "write")
        assert payload["available"] is True
        assert payload["selected_topic"] == "SELECT"
        assert payload["selected_difficulty"] == "beginner"
        assert payload["exercise"]["concept"].upper() == "SELECT"
        assert payload["exercise"]["difficulty"] == "beginner"
    finally:
        app.close()


def post_json(port: int, path: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())


def get_json(port: int, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}{path}", timeout=10
    ) as response:
        return response.status, json.loads(response.read().decode())


def create_test_server(app: TutorWebApp):
    """Build the real serve() Handler bound to ``app`` for tests."""
    import inspect
    import textwrap

    from sql_tutor import web as web_module

    source = inspect.getsource(web_module.serve)
    start = source.index("    class Handler(")
    end = source.index(
        "    server = ThreadingHTTPServer((host, port), Handler)"
    )
    raw = textwrap.dedent(source[start:end]).rstrip()
    factory_src = (
        "def _make_test_handler(app):\n"
        + textwrap.indent(raw, "    ")
        + "\n    return Handler\n"
    )
    namespace: dict = {}
    exec(factory_src, vars(web_module), namespace)
    return namespace["_make_test_handler"](app)


@pytest.fixture
def live_server(tmp_path: Path):
    """Run the real HTTP stack (TutorWebApp + serve() handlers)."""
    settings = Settings(
        data_dir=Path("data"), database_path=tmp_path / "progress.db"
    )
    app = TutorWebApp(settings)
    handler_cls = create_test_server(app)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app.close()


def test_http_error_paths_return_json(live_server: int) -> None:
    port = live_server
    status, session = get_json(port, "/api/session")
    assert status == 200
    assert session["exercise"]["id"]

    status, missing = get_json(port, "/api/config")
    assert status == 200
    assert missing["provider"] == "mock"

    status, bad_topic = post_json(
        port, "/api/topic", {"concept": "NOT A TOPIC"}
    )
    assert status == 400
    assert "Unknown curriculum topic" in bad_topic["error"]

    status, empty = post_json(port, "/api/submit", {"query": "   "})
    assert status == 400
    assert "cannot be empty" in empty["error"]

    status, bad_difficulty = post_json(
        port, "/api/difficulty", {"difficulty": "impossible"}
    )
    assert status == 400
    assert "Unknown difficulty" in bad_difficulty["error"]

    status, bad_type = post_json(
        port, "/api/question-type", {"question_type": "explain"}
    )
    assert status == 400
    assert "Unsupported question type" in bad_type["error"]

    status, unknown = post_json(port, "/api/nope", {})
    assert status == 404
    assert unknown["error"] == "Not found"


def test_http_submit_next_skip_hint_progress_flow(live_server: int) -> None:
    port = live_server
    status, session = get_json(port, "/api/session")
    assert status == 200
    first_id = session["exercise"]["id"]

    status, wrong = post_json(
        port, "/api/submit", {"query": "SELECT id FROM employees;"}
    )
    assert status == 200
    assert wrong["feedback"]["is_correct"] is False
    assert wrong["attempts"] == 1

    status, hint = post_json(port, "/api/hint", {})
    assert status == 200
    assert hint["hint"]

    status, progress = get_json(port, "/api/progress")
    assert status == 200
    assert progress["items"]

    status, skipped = post_json(port, "/api/skip", {})
    assert status == 200
    assert skipped["exercise"]["id"] != first_id

    status, advanced = post_json(port, "/api/next", {})
    assert status == 200
    assert advanced["exercise"]["id"] not in {first_id, skipped["exercise"]["id"]}

    status, generated = post_json(
        port,
        "/api/generate",
        {"concept": "SELECT", "difficulty": "beginner",
         "question_type": "write"},
        )
    assert status == 200
    assert generated["exercise"]["concept"].upper() == "SELECT"


def test_http_predict_endpoint(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    handler_cls = create_test_server(app)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]

        # The app starts on a write exercise; ask for a predict answer.
        app.choose_question_type("predict")
        exercise = app.session.current
        assert exercise is not None
        correct = app.session.expected_output()

        status, body = post_json(port, "/api/predict", {"prediction": correct})
        assert status == 200
        assert body["feedback"]["is_correct"] is True
        assert body["actual_output"]

        # Wrong prediction
        status, body2 = post_json(port, "/api/predict", {"prediction": "zzz | zzz"})
        assert status == 200
        assert body2["feedback"]["is_correct"] is False

        # Empty prediction is rejected
        status, body3 = post_json(port, "/api/predict", {"prediction": "   "})
        assert status == 400
        assert "cannot be empty" in body3["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app.close()
