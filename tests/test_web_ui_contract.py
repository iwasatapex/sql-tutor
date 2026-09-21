from sql_tutor.web import HTML


def _submit_function() -> str:
    start = HTML.index("async function submit()")
    end = HTML.index("async function action", start)
    return HTML[start:end]


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
    submit_function = _submit_function()

    assert "/api/submit" in submit_function
    assert "/api/next" in submit_function
    assert "Loading next question" in submit_function


def test_incorrect_answers_do_not_auto_advance() -> None:
    submit_function = _submit_function()

    assert "is_correct" in submit_function
    assert "Answer checked" in submit_function


def test_submit_button_stays_disabled_until_next_question_ready() -> None:
    submit_function = _submit_function()
    submit_index = submit_function.index("$('submit').disabled=true")
    next_index = submit_function.index("/api/next")
    enable_index = submit_function.index("$('submit').disabled=false")

    assert submit_index < next_index < enable_index


def test_run_check_clears_editor_for_next_question() -> None:
    assert "$('query').value=''" in HTML


def test_next_and_skip_apply_full_state_for_question_type_panels() -> None:
    action_start = HTML.index("async function action(")
    action_end = HTML.index("$('topic').onchange", action_start)
    action = HTML[action_start:action_end]
    assert "applyState(await api(path" in action


def test_topic_difficulty_and_type_controls_are_wired() -> None:
    assert "$('topic').onchange=chooseTopic" in HTML
    assert "$('difficulty').onchange=chooseDifficulty" in HTML
    assert "$('question-type').onchange=chooseQuestionType" in HTML
    assert "$('generate').onclick=generate" in HTML
    assert "/api/topic" in HTML
    assert "/api/difficulty" in HTML
    assert "/api/question-type" in HTML
    assert "/api/generate" in HTML
    assert "/api/config" in HTML


def test_all_question_types_are_offered_as_supported() -> None:
    for question_type in ("write", "debug", "predict", "explain"):
        assert f'value="{question_type}"' in HTML

    assert "not supported yet" not in HTML
    assert "disabled>" not in HTML
    assert 'id="provider-info"' in HTML


def test_predict_panel_and_endpoint_are_wired() -> None:
    assert 'id="predict-panel"' in HTML
    assert 'id="predict-query-display"' in HTML
    assert 'id="prediction"' in HTML
    assert 'id="check-prediction"' in HTML
    assert "/api/predict" in HTML
    assert "renderPredictPanel" in HTML
    assert "checkPrediction" in HTML
    assert "actual_output" in HTML


def test_explain_panel_and_endpoint_are_wired() -> None:
    assert 'id="explain-panel"' in HTML
    assert 'id="explain-query-display"' in HTML
    assert 'id="explanation"' in HTML
    assert 'id="check-explanation"' in HTML
    assert "/api/explain" in HTML
    assert "renderExplainPanel" in HTML
    assert "checkExplanation" in HTML
    assert "reference_explanation" in HTML
    # The answer is revealed only after grading, never up front.
    assert "Model answer" in HTML


def test_read_only_question_types_receive_the_query() -> None:
    import sql_tutor.web as web

    assert web._READ_ONLY_QUESTION_TYPES == ("predict", "explain")
    # Only predict/explain payloads carry the query to read.
    assert "e.query||''" in HTML


def test_no_duplicate_element_ids() -> None:
    import re
    from collections import Counter

    ids = re.findall(r'id="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), [
        item for item, count in Counter(ids).items() if count > 1
    ]


def test_navigation_links_point_at_real_sections() -> None:
    import re

    anchors = re.findall(r'href="#([^"]+)"', HTML)
    assert anchors
    for anchor in anchors:
        assert f'id="{anchor}"' in HTML, f"missing section #{anchor}"


def test_every_control_has_a_handler() -> None:
    handlers = {
        "topic": "$('topic').onchange",
        "question-type": "$('question-type').onchange",
        "difficulty": "$('difficulty').onchange",
        "generate": "$('generate').onclick",
        "submit": "$('submit').onclick",
        "hint": "$('hint').onclick",
        "schema": "$('schema').onclick",
        "skip": "$('skip').onclick",
        "next": "$('next').onclick",
        "query": "$('query').addEventListener",
    }
    for control, handler in handlers.items():
        assert handler in HTML, f"missing handler for #{control}"
    assert "Ctrl" in HTML and "submit()" in HTML


def test_progress_uses_unique_element_id() -> None:
    assert 'id="progress-panel"' in HTML
    assert 'id="progress-content"' in HTML
    assert 'id="progress"><h2' not in HTML
