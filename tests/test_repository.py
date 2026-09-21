from pathlib import Path

import pytest

from sql_tutor.exercises.repository import (
    ExerciseLoadError,
    ExerciseRepository,
    exercise_to_payload,
)
from sql_tutor.exercises.verifier import verify_exercise
from sql_tutor.learning.curriculum import Curriculum

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def repository() -> ExerciseRepository:
    return ExerciseRepository.from_directory(DATA_DIR)


def test_bundled_exercises_load(repository: ExerciseRepository) -> None:
    assert len(repository) >= 24


def test_every_bundled_exercise_is_solvable(
    repository: ExerciseRepository,
) -> None:
    for exercise in repository.all():
        result = verify_exercise(exercise)
        assert result.is_valid, (exercise.exercise_id, result.errors)


def test_catalog_topics_have_exercises_and_new_topics_are_generation_ready(
    repository: ExerciseRepository,
) -> None:
    catalog_topics = {exercise.concept for exercise in repository.all()}
    curriculum_topics = {topic.title for topic in Curriculum.default().topics}

    # Existing curated topics retain their catalog coverage. New curriculum
    # topics are intentionally generation-first and may have no static files.
    for concept in catalog_topics:
        assert len(repository.for_concept(concept)) >= 3, concept
    assert catalog_topics <= curriculum_topics


def test_for_concept_is_case_insensitive(
    repository: ExerciseRepository,
) -> None:
    assert repository.for_concept("group by") == repository.for_concept(
        "GROUP BY"
    )


def test_duplicate_ids_are_rejected(
    repository: ExerciseRepository,
) -> None:
    exercise = repository.all()[0]

    with pytest.raises(ExerciseLoadError):
        repository.add(exercise)


def test_inline_exercise_round_trips(
    repository: ExerciseRepository,
    tmp_path: Path,
) -> None:
    import json

    original = repository.get("select-01")
    assert original is not None

    target = tmp_path / "exercises"
    target.mkdir()
    (target / "one.json").write_text(
        json.dumps([exercise_to_payload(original)])
    )

    loaded = ExerciseRepository.from_directory(tmp_path).get("select-01")

    assert loaded == original


def test_malformed_exercise_file_reports_filename(tmp_path: Path) -> None:
    target = tmp_path / "exercises"
    target.mkdir()
    (target / "broken.json").write_text('[{"exercise_id": "x"}]')

    with pytest.raises(ExerciseLoadError, match="broken.json"):
        ExerciseRepository.from_directory(tmp_path)


def test_string_values_with_quotes_are_escaped(tmp_path: Path) -> None:
    import json

    (tmp_path / "datasets").mkdir()
    (tmp_path / "exercises").mkdir()
    (tmp_path / "datasets" / "d.json").write_text(json.dumps({
        "name": "d",
        "tables": [{
            "name": "people",
            "columns": [{"name": "name", "data_type": "TEXT"}],
            "rows": [["O'Brien"]],
        }],
    }))
    (tmp_path / "exercises" / "e.json").write_text(json.dumps([{
        "exercise_id": "q", "title": "t", "description": "d",
        "concept": "SELECT", "difficulty": "beginner", "dataset": "d",
        "expected_query": "SELECT name FROM people;",
    }]))

    exercise = ExerciseRepository.from_directory(tmp_path).get("q")

    assert exercise is not None
    assert verify_exercise(exercise).is_valid
