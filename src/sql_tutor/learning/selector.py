from dataclasses import dataclass

from sql_tutor.exercises.models import Exercise, ExerciseDifficulty
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.difficulty import DifficultyAdjuster
from sql_tutor.storage.progress import ProgressStore


@dataclass(frozen=True)
class ExerciseSelection:
    exercise: Exercise
    reason: str


class ExerciseSelector:
    def __init__(
        self,
        curriculum: Curriculum | None = None,
        difficulty_adjuster: DifficultyAdjuster | None = None,
    ) -> None:
        self.curriculum = curriculum or Curriculum.default()
        self.difficulty_adjuster = difficulty_adjuster or DifficultyAdjuster()

    def select(
        self,
        exercises: tuple[Exercise, ...],
        progress_store: ProgressStore,
    ) -> ExerciseSelection:
        if not exercises:
            raise ValueError("At least one exercise is required")

        difficulty_order = {
            ExerciseDifficulty.BEGINNER: 0,
            ExerciseDifficulty.INTERMEDIATE: 1,
            ExerciseDifficulty.ADVANCED: 2,
        }
        ranked: list[tuple[int, int, int, Exercise]] = []
        for exercise in exercises:
            attempts = progress_store.get_attempts(exercise.exercise_id)
            results = tuple(attempt.is_correct for attempt in attempts)
            target = self.difficulty_adjuster.adjust(exercise.difficulty, results)
            mastery = progress_store.get_mastery(exercise.exercise_id)
            topic = self.curriculum.get_topic(exercise.concept)
            topic_order = topic.order if topic else 999
            # Unattempted and low-accuracy exercises come first; ties favor
            # curriculum order and the difficulty recommended by recent results.
            familiarity = len(attempts)
            ranked.append(
                (
                    round(mastery.accuracy * 100),
                    familiarity,
                    topic_order + abs(difficulty_order[target] - difficulty_order[exercise.difficulty]),
                    exercise,
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3].exercise_id))
        selected = ranked[0][3]
        return ExerciseSelection(
            exercise=selected,
            reason=f"Selected {selected.exercise_id} for targeted practice.",
        )
