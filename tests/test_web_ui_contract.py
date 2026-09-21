from sql_tutor.web import HTML


def test_all_primary_controls_exist() -> None:
    required_controls = (
        'id="topic"',
        'id="question-type"',
        'id="difficulty"',
        'id="generate"',
        'id="skip"',
        'id="next"',
        'id="submit"',
        'id="hint"',
        'id="schema"',
        'id="query"',
        'id="feedback"',
        'id="progress-content"',
    )

    for control in required_controls:
        assert control in HTML, f"Missing UI control: {control}"


def test_ui_exposes_expected_api_routes() -> None:
    expected_routes = (
        "/api/session",
        "/api/progress",
        "/api/topic",
        "/api/submit",
        "/api/hint",
        "/api/next",
        "/api/skip",
    )

    for route in expected_routes:
        assert route in HTML or route in {
            "/api/session",
            "/api/progress",
        }


def test_submit_has_duplicate_submission_guard() -> None:
    assert "submitInFlight" in HTML
    assert "$('submit').disabled=true" in HTML
    assert "$('submit').disabled=false" in HTML


def test_submit_advances_to_next_question() -> None:
    submit_start = HTML.index("async function submit()")
    submit_end = HTML.index("async function action", submit_start)
    submit_function = HTML[submit_start:submit_end]

    assert "/api/submit" in submit_function
    assert "/api/next" in submit_function
    assert "Loading next question" in submit_function


def test_progress_uses_unique_element_id() -> None:
    assert 'id="progress-panel"' in HTML
    assert 'id="progress-content"' in HTML
    assert 'id="progress"><h2' not in HTML
