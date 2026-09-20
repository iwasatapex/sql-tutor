import json
from pathlib import Path

from sql_tutor.exercises.generator import ExerciseGenerator
from sql_tutor.exercises.models import Exercise, ExerciseDifficulty
from sql_tutor.llm.base import LLMProvider


def load_exercises(path: str | Path) -> tuple[Exercise, ...]:
    payload = json.loads(Path(path).read_text())
    return tuple(
        ExerciseGenerator._parse_exercise(item)
        for item in payload
    )


def generate_exercise(
    provider: LLMProvider,
    concept: str,
    difficulty: ExerciseDifficulty,
) -> Exercise:
    return ExerciseGenerator(provider).generate(concept, difficulty)
