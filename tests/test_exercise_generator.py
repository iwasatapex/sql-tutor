import json

import pytest

from sql_tutor.exercises.generator import (
    ExerciseGenerationError,
    ExerciseGenerator,
)
from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.llm.mock import MockLLMProvider


def valid_payload() -> dict:
    return {
        "exercise_id": "select-users",
        "title": "Select Users",
        "description": "Retrieve all users.",
        "concept": "SELECT",
        "difficulty": "beginner",
        "schema": [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "data_type": "INTEGER"},
                    {"name": "name", "data_type": "TEXT"},
                ],
            }
        ],
        "expected_query": "SELECT * FROM users;",
    }


def test_generator_returns_exercise() -> None:
    provider = MockLLMProvider(
        response=json.dumps(valid_payload())
    )

    generator = ExerciseGenerator(provider)
    exercise = generator.generate(
        concept="SELECT",
        difficulty=ExerciseDifficulty.BEGINNER,
    )

    assert exercise.exercise_id == "select-users"
    assert exercise.difficulty == ExerciseDifficulty.BEGINNER


def test_generator_rejects_invalid_json() -> None:
    provider = MockLLMProvider(response="not valid JSON")

    generator = ExerciseGenerator(provider)

    with pytest.raises(ExerciseGenerationError):
        generator.generate(
            concept="SELECT",
            difficulty=ExerciseDifficulty.BEGINNER,
        )


def test_generator_rejects_unsafe_query() -> None:
    payload = valid_payload()
    payload["expected_query"] = "DROP TABLE users;"

    provider = MockLLMProvider(response=json.dumps(payload))
    generator = ExerciseGenerator(provider)

    with pytest.raises(ExerciseGenerationError):
        generator.generate(
            concept="SELECT",
            difficulty=ExerciseDifficulty.BEGINNER,
        )


def test_generator_normalizes_difficulty_case() -> None:
    payload = valid_payload()
    payload["difficulty"] = "Advanced"
    provider = MockLLMProvider(response=json.dumps(payload))

    generator = ExerciseGenerator(provider)
    exercise = generator.generate(
        concept="SELECT",
        difficulty=ExerciseDifficulty.ADVANCED,
    )

    assert exercise.difficulty == ExerciseDifficulty.ADVANCED
