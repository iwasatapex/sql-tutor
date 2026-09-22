from collections.abc import Collection, Sequence
from dataclasses import dataclass

from sql_tutor.exercises.models import Exercise, ExerciseDifficulty
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.learning.curriculum import Curriculum, CurriculumTopic
from sql_tutor.learning.difficulty import DifficultyAdjuster
from sql_tutor.learning.mastery import (
    MasteryLevel,
    MasteryResult,
    MasteryTracker,
)
from sql_tutor.storage.progress import Attempt

_DIFFICULTY_ORDER = (
    ExerciseDifficulty.BEGINNER,
    ExerciseDifficulty.INTERMEDIATE,
    ExerciseDifficulty.ADVANCED,
)


@dataclass(frozen=True)
class TopicProgress:
    topic: CurriculumTopic
    attempts: int
    solved: int
    total_exercises: int
    mastery: MasteryResult
    is_complete: bool


class ExerciseSelector:
    """Choose the next exercise from curriculum, mastery and difficulty.

    A topic is complete when every exercise in it is solved, or when the
    learner has solved ``min_solved`` distinct exercises and is at least
    proficient over their most recent ``window`` attempts on the topic.
    Within the current topic the target difficulty starts at the topic's
    own level and is moved by ``DifficultyAdjuster`` using recent results.
    """

    def __init__(
        self,
        curriculum: Curriculum,
        repository: ExerciseRepository,
        *,
        mastery_tracker: MasteryTracker | None = None,
        difficulty_adjuster: DifficultyAdjuster | None = None,
        window: int = 5,
        min_solved: int = 2,
    ) -> None:
        self.curriculum = curriculum
        self.repository = repository
        self.mastery_tracker = mastery_tracker or MasteryTracker()
        self.difficulty_adjuster = difficulty_adjuster or DifficultyAdjuster()
        self.window = window
        self.min_solved = min_solved

    def topic_progress(
        self,
        attempts: Sequence[Attempt],
    ) -> tuple[TopicProgress, ...]:
        results_by_concept: dict[str, list[bool]] = {}
        solved_by_concept: dict[str, set[str]] = {}

        for attempt in attempts:
            exercise = self.repository.get(attempt.exercise_id)

            if exercise is None:
                continue

            concept = exercise.concept.upper()
            results_by_concept.setdefault(concept, []).append(
                attempt.is_correct
            )

            if attempt.is_correct:
                solved_by_concept.setdefault(concept, set()).add(
                    exercise.exercise_id
                )

        progress: list[TopicProgress] = []

        for topic in self.curriculum.topics:
            key = topic.title.upper()
            results = results_by_concept.get(key, [])
            solved = len(solved_by_concept.get(key, set()))
            total = len(self.repository.for_concept(topic.title))
            mastery = self.mastery_tracker.calculate(
                tuple(results[-self.window:])
            )

            all_solved = total > 0 and solved >= total
            proficient = mastery.level in (
                MasteryLevel.PROFICIENT,
                MasteryLevel.MASTERED,
            )

            progress.append(
                TopicProgress(
                    topic=topic,
                    attempts=len(results),
                    solved=solved,
                    total_exercises=total,
                    mastery=mastery,
                    is_complete=all_solved
                    or (solved >= self.min_solved and proficient),
                )
            )

        return tuple(progress)

    def generation_target_for_concept(
        self,
        concept: str,
        attempts: Sequence[Attempt],
    ) -> tuple[str, ExerciseDifficulty]:
        """Return a generation target for an explicitly selected topic."""
        topic = self.curriculum.get_topic(concept)
        if topic is None:
            raise ValueError(f"Unknown curriculum topic: {concept}")
        return (topic.title, self._target_difficulty(topic, attempts))

    def generation_target(
        self,
        attempts: Sequence[Attempt],
    ) -> tuple[str, ExerciseDifficulty]:
        """Return the next concept and adaptive difficulty for generation."""
        progress_items = self.topic_progress(attempts)
        for progress in progress_items:
            if not progress.is_complete:
                return (
                    progress.topic.title,
                    self._target_difficulty(progress.topic, attempts),
                )

        # Once every topic is complete, continue with the least-mastered topic.
        fallback = min(
            progress_items,
            key=lambda item: (item.mastery.accuracy, item.topic.order),
        )
        return (
            fallback.topic.title,
            self._target_difficulty(fallback.topic, attempts),
        )

    def select_next(
        self,
        attempts: Sequence[Attempt],
        *,
        exclude_ids: Collection[str] = (),
        concept: str | None = None,
        difficulty: ExerciseDifficulty | None = None,
        question_type: str | None = None,
    ) -> Exercise | None:
        solved_ids = {a.exercise_id for a in attempts if a.is_correct}
        unavailable = solved_ids | set(exclude_ids)

        # Determine which question types to include.
        if question_type is None:
            allowed_types: set[str] = set()
        else:
            allowed_types = {question_type.strip().lower()}

        for progress in self.topic_progress(attempts):
            if concept is not None and progress.topic.title.upper() != concept.strip().upper():
                continue
            if progress.is_complete:
                continue

            candidates = list(
                self.repository.for_concept(progress.topic.title)
            )

            candidates = [
                e for e in candidates
                if e.exercise_id not in unavailable
            ]

            if allowed_types:
                candidates = [
                    e for e in candidates
                    if e.question_type.value in allowed_types
                ]

            if not candidates:
                continue

            if difficulty is not None:
                matching = [
                    e for e in candidates if e.difficulty == difficulty
                ]
                if matching:
                    candidates = matching

            target = (
                difficulty
                if difficulty is not None
                else self._target_difficulty(progress.topic, attempts)
            )

            return min(
                candidates,
                key=lambda e: (
                    abs(
                        _DIFFICULTY_ORDER.index(e.difficulty)
                        - _DIFFICULTY_ORDER.index(target)
                    ),
                    _DIFFICULTY_ORDER.index(e.difficulty),
                    e.exercise_id,
                ),
            )

        return None

    def _target_difficulty(
        self,
        topic: CurriculumTopic,
        attempts: Sequence[Attempt],
    ) -> ExerciseDifficulty:
        recent: list[bool] = []

        for attempt in attempts:
            exercise = self.repository.get(attempt.exercise_id)

            if exercise and exercise.concept.upper() == topic.title.upper():
                recent.append(attempt.is_correct)

        return self.difficulty_adjuster.adjust(
            topic.difficulty,
            tuple(recent[-self.window:]),
        )
