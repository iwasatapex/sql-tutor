from sql_tutor.sql.comparator import compare_results
from sql_tutor.sql.engine import QueryResult


def test_matching_results_are_correct() -> None:
    result = QueryResult(
        columns=("id", "name"),
        rows=((1, "Alice"), (2, "Bob")),
    )

    comparison = compare_results(result, result)

    assert comparison.is_correct is True


def test_different_rows_are_incorrect() -> None:
    actual = QueryResult(
        columns=("id",),
        rows=((1,),),
    )
    expected = QueryResult(
        columns=("id",),
        rows=((2,),),
    )

    comparison = compare_results(actual, expected)

    assert comparison.is_correct is False


def test_row_order_can_be_ignored() -> None:
    actual = QueryResult(
        columns=("id",),
        rows=((2,), (1,)),
    )
    expected = QueryResult(
        columns=("id",),
        rows=((1,), (2,)),
    )

    comparison = compare_results(
        actual,
        expected,
        ignore_row_order=True,
    )

    assert comparison.is_correct is True


def test_column_order_must_match() -> None:
    actual = QueryResult(
        columns=("name", "id"),
        rows=(("Alice", 1),),
    )
    expected = QueryResult(
        columns=("id", "name"),
        rows=((1, "Alice"),),
    )

    comparison = compare_results(actual, expected)

    assert comparison.is_correct is False
