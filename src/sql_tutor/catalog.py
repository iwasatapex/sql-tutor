import json
from pathlib import Path

from sql_tutor.exercises.generator import ExerciseGenerator
from sql_tutor.exercises.models import Exercise, ExerciseDifficulty
from sql_tutor.exercises.validator import validate_exercise
from sql_tutor.llm.base import LLMProvider


def load_exercises(path: str | Path) -> tuple[Exercise, ...]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("exercises")
    if not isinstance(payload, list):
        raise ValueError("Exercise catalog must contain a JSON list or an 'exercises' list.")

    exercises: list[Exercise] = []
    seen_ids: set[str] = set()
    for item in payload:
        exercise = ExerciseGenerator._parse_exercise(item)
        if exercise.exercise_id in seen_ids:
            raise ValueError(f"Duplicate exercise_id: {exercise.exercise_id}")
        validation = validate_exercise(exercise)
        if not validation.is_valid:
            raise ValueError(
                f"Invalid exercise {exercise.exercise_id}: " + "; ".join(validation.errors)
            )
        seen_ids.add(exercise.exercise_id)
        exercises.append(exercise)
    return tuple(exercises)


def generate_exercise(
    provider: LLMProvider,
    concept: str,
    difficulty: ExerciseDifficulty,
) -> Exercise:
    return ExerciseGenerator(provider).generate(concept, difficulty)
