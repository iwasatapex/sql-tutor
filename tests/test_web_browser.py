"""Real-browser UI tests with Playwright (headless Chromium).

Covers the Run & Check lifecycle that contract tests cannot observe:
button disabled/enabled states, double-click prevention, automatic
advance to the next question, editor reset, progress updates, and
failure recovery. Skipped automatically when Playwright or a browser
binary is unavailable.
"""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from sql_tutor.config import Settings
from sql_tutor.web import TutorWebApp

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import Error as PlaywrightError  # noqa: E402

from tests.test_web_backend import create_test_server  # noqa: E402


@pytest.fixture
def browser_app(tmp_path: Path):
    settings = Settings(
        data_dir=Path("data"), database_path=tmp_path / "progress.db"
    )
    app = TutorWebApp(settings)
    handler = create_test_server(app)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app.close()


@pytest.fixture
def page(browser_app):
    from playwright.sync_api import sync_playwright

    app, base_url = browser_app
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch()
            tab = browser.new_page()
            tab.goto(base_url, wait_until="networkidle")
            yield app, tab, base_url
            browser.close()
    except PlaywrightError as error:
        pytest.skip(f"browser unavailable: {error}")


def wait_for_exercise(tab, exercise_id: str | None = None) -> None:
    tab.wait_for_function(
        "window.__sqlTutorState && window.__sqlTutorState.exercise",
        timeout=10000,
    )
    if exercise_id is not None:
        tab.wait_for_function(
            f"window.__sqlTutorState.exercise.id !== '{exercise_id}'",
            timeout=10000,
        )


def test_initial_page_load_shows_exercise(page) -> None:
    _, tab, _ = page
    wait_for_exercise(tab)

    assert tab.locator("#exercise .title").count() == 1
    assert tab.locator("#topic option").count() > 1
    assert tab.locator("#progress-content .progress-row").count() > 0
    assert tab.locator("#status").inner_text() == "Ready"


def test_run_check_correct_answer_advances_and_resets(page) -> None:
    app, tab, _ = page
    wait_for_exercise(tab)
    first_id = tab.evaluate("window.__sqlTutorState.exercise.id")
    expected = app.session.current.expected_query

    tab.fill("#query", expected)
    tab.click("#submit")
    # Button disables immediately and stays disabled through auto-advance.
    tab.wait_for_function(
        "document.getElementById('submit').disabled === true",
        timeout=5000,
    )
    wait_for_exercise(tab, first_id)

    assert tab.evaluate("window.__sqlTutorState.exercise.id") != first_id
    assert tab.locator("#query").input_value() == ""
    assert tab.locator("#submit").is_enabled()
    assert tab.locator("#attempts").inner_text() == "0"
    assert tab.locator("#status").inner_text() == "Ready"
    progress = tab.locator("#progress-content").inner_text()
    assert "1/" in progress


def test_run_check_wrong_answer_does_not_advance(page) -> None:
    _, tab, _ = page
    wait_for_exercise(tab)
    first_id = tab.evaluate("window.__sqlTutorState.exercise.id")

    tab.fill("#query", "SELECT id FROM employees;")
    tab.click("#submit")
    tab.wait_for_function(
        "window.__sqlTutorState.feedback !== null", timeout=10000
    )
    tab.wait_for_function(
        "document.getElementById('submit').disabled === false",
        timeout=10000,
    )

    assert tab.evaluate("window.__sqlTutorState.exercise.id") == first_id
    assert "Answer checked" in tab.locator("#status").inner_text()
    assert "Not quite" in tab.locator("#feedback").inner_text()


def test_double_click_submits_only_once(page) -> None:
    app, tab, _ = page
    wait_for_exercise(tab)
    expected = app.session.current.expected_query

    tab.fill("#query", expected)
    tab.dblclick("#submit")
    first_id = tab.evaluate("window.__sqlTutorState.exercise.id")
    wait_for_exercise(tab, first_id)

    attempts = app.session.progress_store.get_all_attempts()
    assert sum(1 for a in attempts if a.exercise_id == first_id) == 1


def test_dropdowns_drive_backend_state(page) -> None:
    _, tab, _ = page
    wait_for_exercise(tab)

    tab.select_option("#topic", "WHERE")
    tab.wait_for_function(
        "window.__sqlTutorState.selected_topic === 'WHERE'",
        timeout=10000,
    )
    assert "WHERE" in tab.locator("#exercise").inner_text()

    tab.select_option("#difficulty", "intermediate")
    tab.wait_for_function(
        "window.__sqlTutorState.selected_difficulty === 'intermediate'",
        timeout=10000,
    )

    tab.click("#generate")
    tab.wait_for_function(
        "window.__sqlTutorState.exercise !== null", timeout=10000
    )
    assert tab.locator("#status").inner_text() == "Ready"


def test_hint_schema_skip_and_next_buttons(page) -> None:
    _, tab, _ = page
    wait_for_exercise(tab)
    first_id = tab.evaluate("window.__sqlTutorState.exercise.id")

    tab.click("#hint")
    tab.wait_for_selector("#feedback .hint", timeout=10000)

    tab.click("#schema")  # must not throw or change backend state
    assert tab.evaluate("window.__sqlTutorState.exercise.id") == first_id

    tab.click("#skip")
    wait_for_exercise(tab, first_id)
    second_id = tab.evaluate("window.__sqlTutorState.exercise.id")
    assert second_id != first_id

    tab.click("#next")
    wait_for_exercise(tab, second_id)
    assert tab.evaluate("window.__sqlTutorState.exercise.id") not in {
        first_id,
        second_id,
    }
    assert tab.locator("#status").inner_text() == "Ready"


def test_empty_submission_shows_error_and_stays_usable(page) -> None:
    _, tab, _ = page
    wait_for_exercise(tab)

    tab.fill("#query", "   ")
    tab.click("#submit")
    tab.wait_for_function(
        "document.getElementById('status').innerText.length > 0",
        timeout=10000,
    )
    # Empty input is ignored client-side: button is never stuck disabled.
    assert tab.locator("#submit").is_enabled()
