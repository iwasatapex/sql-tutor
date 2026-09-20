import sqlite3

from sql_tutor.exercises.models import Exercise
from sql_tutor.exercises.validator import (
    ExerciseValidationResult,
    validate_exercise,
)
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.sql.safety import UnsafeQueryError


def verify_exercise(exercise: Exercise) -> ExerciseValidationResult:
    """Validate an exercise and prove it is solvable.

    Builds the exercise's database from ``setup_sql`` and runs the expected
    query. The expected query must execute and return at least one row,
    and every schema table must exist in the built database.
    """
    structural = validate_exercise(exercise)
    errors = list(structural.errors)

    if not exercise.setup_sql:
        errors.append("Exercise has no setup_sql, so it cannot be verified")
        return ExerciseValidationResult(False, tuple(errors))

    if errors:
        return ExerciseValidationResult(False, tuple(errors))

    engine = SQLEngine()

    try:
        engine.execute_setup(list(exercise.setup_sql))

        for table in exercise.schema:
            try:
                engine.execute_query(f"SELECT * FROM {table.name} LIMIT 1;")
            except sqlite3.Error:
                errors.append(
                    f"Schema table {table.name} was not created by setup_sql"
                )

        if not errors:
            result = engine.execute_query(exercise.expected_query)

            if not result.rows:
                errors.append("Expected query returns no rows")
    except (sqlite3.Error, UnsafeQueryError, ValueError) as error:
        errors.append(f"Exercise could not be built or run: {error}")
    finally:
        engine.close()

    return ExerciseValidationResult(
        is_valid=not errors,
        errors=tuple(errors),
    )
