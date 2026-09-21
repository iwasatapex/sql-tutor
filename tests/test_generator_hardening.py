import json

import pytest

from sql_tutor.exercises.generator import (
    ExerciseGenerationError,
    ExerciseGenerator,
)
from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.models import LLMRequest, LLMResponse


def payload(**overrides) -> dict:
    base = {
        "exercise_id": "adults",
        "title": "Adults",
        "description": "Return names of adults.",
        "concept": "WHERE",
        "difficulty": "beginner",
        "schema": [{"name": "people", "columns": [
            {"name": "name", "data_type": "TEXT"},
            {"name": "age", "data_type": "INTEGER"},
        ]}],
        "setup_sql": [
            "CREATE TABLE people (name TEXT, age INTEGER)",
            "INSERT INTO people VALUES ('Ann', 30)",
            "INSERT INTO people VALUES ('Tim', 10)",
        ],
        "expected_query": "SELECT name FROM people WHERE age >= 18;",
    }
    base.update(overrides)
    return base


class ScriptedProvider(LLMProvider):
    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        reply = self.replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        return LLMResponse(content=reply, model="scripted")


def generate(provider: LLMProvider, **kwargs):
    return ExerciseGenerator(provider, **kwargs).generate(
        "WHERE", ExerciseDifficulty.BEGINNER
    )


def test_markdown_fences_are_stripped() -> None:
    reply = "```json\n" + json.dumps(payload()) + "\n```"

    assert generate(ScriptedProvider(reply)).exercise_id == "adults"


def test_request_asks_for_json_mode() -> None:
    provider = ScriptedProvider(json.dumps(payload()))
    generate(provider)

    assert provider.requests[0].json_mode is True


def test_retries_with_error_feedback() -> None:
    provider = ScriptedProvider("not json", json.dumps(payload()))

    exercise = generate(provider, max_attempts=2)

    assert exercise.exercise_id == "adults"
    assert "rejected" in provider.requests[1].prompt


def test_provider_errors_are_retried_then_reported() -> None:
    provider = ScriptedProvider(LLMProviderError("down"), LLMProviderError("down"))

    with pytest.raises(ExerciseGenerationError, match="down"):
        generate(provider, max_attempts=2)


def test_gives_up_after_max_attempts() -> None:
    provider = ScriptedProvider("x", "y", "z")

    with pytest.raises(ExerciseGenerationError):
        generate(provider, max_attempts=3)

    assert provider.replies == []


def test_verify_accepts_working_exercise() -> None:
    exercise = generate(
        ScriptedProvider(json.dumps(payload())), verify=True
    )

    assert exercise.setup_sql


def test_verify_rejects_query_returning_no_rows() -> None:
    bad = payload(expected_query="SELECT name FROM people WHERE age > 100;")

    with pytest.raises(ExerciseGenerationError, match="no rows"):
        generate(ScriptedProvider(json.dumps(bad)), verify=True)


def test_verify_rejects_missing_setup() -> None:
    with pytest.raises(ExerciseGenerationError, match="setup_sql"):
        generate(
            ScriptedProvider(json.dumps(payload(setup_sql=[]))), verify=True
        )


def test_verify_rejects_schema_tables_that_do_not_exist() -> None:
    bad = payload(setup_sql=[
        "CREATE TABLE other (x INTEGER)", "INSERT INTO other VALUES (1)",
    ], expected_query="SELECT x FROM other;")

    with pytest.raises(ExerciseGenerationError, match="was not created"):
        generate(ScriptedProvider(json.dumps(bad)), verify=True)


@pytest.mark.parametrize("statement", [
    "ATTACH DATABASE '/tmp/evil.db' AS evil",
    "DROP TABLE people",
    "PRAGMA writable_schema = ON",
])
def test_setup_sql_is_restricted_to_create_and_insert(statement: str) -> None:
    bad = payload(setup_sql=[statement])

    with pytest.raises(ExerciseGenerationError, match="CREATE TABLE or INSERT"):
        generate(ScriptedProvider(json.dumps(bad)))


def test_setup_sql_must_be_a_list_of_strings() -> None:
    bad = payload(setup_sql={"statement": "CREATE TABLE x (a INTEGER)"})

    with pytest.raises(ExerciseGenerationError):
        generate(ScriptedProvider(json.dumps(bad)))


def test_single_setup_sql_string_is_accepted() -> None:
    ok = payload(setup_sql="CREATE TABLE x (a INTEGER)")

    exercise = generate(ScriptedProvider(json.dumps(ok)))

    assert exercise.setup_sql == ("CREATE TABLE x (a INTEGER)",)
