from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.learning.difficulty import DifficultyAdjuster


def test_increases_difficulty_after_three_correct_answers() -> None:
    adjuster = DifficultyAdjuster()

    result = adjuster.adjust(
        current=ExerciseDifficulty.BEGINNER,
        recent_results=(True, True, True),
    )

    assert result == ExerciseDifficulty.INTERMEDIATE


def test_decreases_difficulty_after_two_incorrect_answers() -> None:
    adjuster = DifficultyAdjuster()

    result = adjuster.adjust(
        current=ExerciseDifficulty.INTERMEDIATE,
        recent_results=(False, False),
    )

    assert result == ExerciseDifficulty.BEGINNER


def test_keeps_difficulty_when_performance_is_mixed() -> None:
    adjuster = DifficultyAdjuster()

    result = adjuster.adjust(
        current=ExerciseDifficulty.INTERMEDIATE,
        recent_results=(True, False, True),
    )

    assert result == ExerciseDifficulty.INTERMEDIATE


def test_difficulty_does_not_exceed_advanced() -> None:
    adjuster = DifficultyAdjuster()

    result = adjuster.adjust(
        current=ExerciseDifficulty.ADVANCED,
        recent_results=(True, True, True),
    )

    assert result == ExerciseDifficulty.ADVANCED


def test_difficulty_does_not_go_below_beginner() -> None:
    adjuster = DifficultyAdjuster()

    result = adjuster.adjust(
        current=ExerciseDifficulty.BEGINNER,
        recent_results=(False, False),
    )

    assert result == ExerciseDifficulty.BEGINNER