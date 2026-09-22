import sqlite3
from dataclasses import dataclass

from sql_tutor.exercises.models import Exercise
from sql_tutor.learning.mastery import MasteryResult
from sql_tutor.llm.base import LLMProvider
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.sql.evaluator import ExerciseEvaluator
from sql_tutor.sql.safety import UnsafeQueryError
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.hints import Hint, HintService
from sql_tutor.tutor.llm_hints import LLMHintService


@dataclass(frozen=True)
class TutorFeedback:
    is_correct: bool
    message: str
    reason: str
    hint: Hint | None = None
    error: str | None = None


class TutorOrchestrator:
    def __init__(
        self,
        progress_store: ProgressStore | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.evaluator = ExerciseEvaluator()
        self.hint_service = HintService()
        self.llm_hint_service = (
            LLMHintService(llm_provider, self.hint_service)
            if llm_provider is not None
            else None
        )
        self.progress_store = progress_store

    def _record_attempt(
        self,
        exercise: Exercise,
        student_query: str,
        is_correct: bool,
        hint_level: int | None,
    ) -> None:
        if self.progress_store is not None:
            self.progress_store.record_attempt(
                exercise_id=exercise.exercise_id,
                student_query=student_query,
                is_correct=is_correct,
                hint_level=hint_level,
            )

    def get_mastery(self, exercise_id: str) -> MasteryResult:
        if self.progress_store is None:
            raise RuntimeError("Progress store is required to retrieve mastery.")
        return self.progress_store.get_mastery(exercise_id)


    def _get_hint(
        self,
        exercise: Exercise,
        level: int,
        student_query: str | None = None,
    ) -> Hint:
        if self.llm_hint_service is not None:
            return self.llm_hint_service.get_hint(
                exercise, level, student_query
            )
        return self.hint_service.get_hint(exercise.concept, level)

    def submit_query(
        self,
        exercise: Exercise,
        engine: SQLEngine,
        student_query: str,
        *,
        hint_level: int | None = None,
        ignore_row_order: bool = False,
    ) -> TutorFeedback:
        try:
            evaluation = self.evaluator.evaluate(
                exercise=exercise,
                engine=engine,
                student_query=student_query,
                ignore_row_order=ignore_row_order,
            )
        except (UnsafeQueryError, sqlite3.Error, ValueError) as error:
            self._record_attempt(
                exercise=exercise,
                student_query=student_query,
                is_correct=False,
                hint_level=hint_level,
            )

            return TutorFeedback(
                is_correct=False,
                message="Your query could not be executed.",
                reason=str(error),
                error=str(error),
            )

        comparison = evaluation.comparison

        if comparison.is_correct:
            message = "Correct! Your query returned the expected result."
            hint = None
        else:
            message = (
                "Not quite. Compare your result with the expected output "
                "and review the relevant SQL concept."
            )
            hint = None

            if hint_level is not None:
                hint = self._get_hint(
                    exercise, hint_level, student_query
                )

        self._record_attempt(
            exercise=exercise,
            student_query=student_query,
            is_correct=comparison.is_correct,
            hint_level=hint_level,
        )

        return TutorFeedback(
            is_correct=comparison.is_correct,
            message=message,
            reason=comparison.reason,
            hint=hint,
        )