import re
from dataclasses import dataclass

from sql_tutor.exercises.models import Exercise
from sql_tutor.sql.safety import UnsafeQueryError, validate_read_only_query


@dataclass(frozen=True)
class ExerciseValidationResult:
    is_valid: bool
    errors: tuple[str, ...]


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EXERCISE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def validate_exercise(exercise: Exercise) -> ExerciseValidationResult:
    errors: list[str] = []

    if not _EXERCISE_ID_PATTERN.fullmatch(exercise.exercise_id):
        errors.append("exercise_id must contain only valid identifier characters")

    table_names: set[str] = set()

    for table in exercise.schema:
        if not _IDENTIFIER_PATTERN.fullmatch(table.name):
            errors.append(f"Invalid table name: {table.name}")

        normalized_table_name = table.name.lower()

        if normalized_table_name in table_names:
            errors.append(f"Duplicate table name: {table.name}")

        table_names.add(normalized_table_name)

        column_names: set[str] = set()

        for column in table.columns:
            if not _IDENTIFIER_PATTERN.fullmatch(column.name):
                errors.append(f"Invalid column name: {column.name}")

            normalized_column_name = column.name.lower()

            if normalized_column_name in column_names:
                errors.append(f"Duplicate column name: {column.name}")

            column_names.add(normalized_column_name)

            if not column.data_type.strip():
                errors.append(f"Column type cannot be empty: {column.name}")

    try:
        validate_read_only_query(exercise.expected_query)
    except UnsafeQueryError as error:
        errors.append(f"Invalid expected query: {error}")

    return ExerciseValidationResult(
        is_valid=not errors,
        errors=tuple(errors),
    )
