from dataclasses import dataclass

from sql_tutor.exercises.models import Exercise
from sql_tutor.sql.comparator import ComparisonResult, compare_results
from sql_tutor.sql.engine import SQLEngine


@dataclass(frozen=True)
class ExerciseEvaluation:
    comparison: ComparisonResult


class ExerciseEvaluator:
    def evaluate(
        self,
        exercise: Exercise,
        engine: SQLEngine,
        student_query: str,
        *,
        ignore_row_order: bool = False,
    ) -> ExerciseEvaluation:
        expected_result = engine.execute_query(
            exercise.expected_query
        )

        actual_result = engine.execute_query(student_query)

        comparison = compare_results(
            actual=actual_result,
            expected=expected_result,
            ignore_row_order=ignore_row_order,
        )

        return ExerciseEvaluation(comparison=comparison)
