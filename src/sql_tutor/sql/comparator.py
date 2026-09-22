from dataclasses import dataclass

from sql_tutor.sql.engine import QueryResult


@dataclass(frozen=True)
class ComparisonResult:
    is_correct: bool
    reason: str


def compare_results(
    actual: QueryResult,
    expected: QueryResult,
    *,
    ignore_row_order: bool = False,
) -> ComparisonResult:
    if actual.columns != expected.columns:
        return ComparisonResult(
            is_correct=False,
            reason="Column names or order do not match.",
        )

    actual_rows = actual.rows
    expected_rows = expected.rows

    if ignore_row_order:
        actual_rows = tuple(sorted(actual_rows, key=repr))
        expected_rows = tuple(sorted(expected_rows, key=repr))

    if actual_rows != expected_rows:
        return ComparisonResult(
            is_correct=False,
            reason="Returned rows do not match the expected result.",
        )

    return ComparisonResult(
        is_correct=True,
        reason="Query results match.",
    )
