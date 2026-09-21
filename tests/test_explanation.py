"""Tests for Explain SQL answer grading."""

import pytest

from sql_tutor.tutor.explanation import (
    DEFAULT_THRESHOLD,
    ExplanationGrade,
    grade_explanation,
    key_terms,
)


def test_key_terms_drops_stopwords_numbers_and_duplicates() -> None:
    reference = (
        "Counts the orders per country, and also lists the total "
        "orders: 12 rows."
    )

    assert key_terms(reference) == ("counts", "orders", "country", "total", "rows")


def test_key_terms_keeps_order_of_first_mention() -> None:
    assert key_terms("Group the orders by status, then count them") == (
        "group",
        "orders",
        "status",
        "count",
    )


def test_grade_accepts_an_answer_covering_the_reference_ideas() -> None:
    reference = "Returns each department name and its employee count."

    grade = grade_explanation(
        "It lists the department names together with how many employees "
        "each department has.",
        reference,
    )

    assert grade.is_gradable is True
    assert grade.is_correct is True
    assert grade.coverage == pytest.approx(0.75)
    # "count" is the one reference idea the answer leaves implicit.
    assert grade.missing == ("count",)


def test_grade_rejects_a_vague_answer_and_names_what_is_missing() -> None:
    reference = "Returns each department name and its employee count."

    grade = grade_explanation("It reads from a table.", reference)

    assert grade.is_correct is False
    assert grade.coverage == 0.0
    assert set(grade.missing) == {"department", "name", "employee", "count"}
    assert grade.missing_terms == "department, name, employee, count"


def test_grade_accepts_plural_and_verb_endings() -> None:
    reference = "Counts the rows grouped by status."

    grade = grade_explanation("Counting row by status group", reference)

    assert grade.is_correct is True
    assert set(grade.matched) == {"counts", "rows", "grouped", "status"}


def test_grade_matches_y_plurals() -> None:
    reference = "Returns each employee salary."

    grade = grade_explanation("It shows the salaries of employees", reference)

    assert set(grade.matched) == {"salary", "employee"}


def test_key_terms_counts_a_word_family_once() -> None:
    assert key_terms("The name and the names of each employee") == (
        "name",
        "employee",
    )


def test_grade_is_threshold_based() -> None:
    reference = "Filters customers by country and orders by status."

    below = grade_explanation("Filters customers", reference)
    above = grade_explanation("Filters customers by status", reference)

    assert below.coverage == pytest.approx(2 / 5)
    assert below.is_correct is False
    assert above.coverage == pytest.approx(3 / 5)
    assert above.is_correct is True


def test_grade_is_case_and_punctuation_insensitive() -> None:
    reference = "Returns the department name, sorted alphabetically."

    assert grade_explanation("DEPARTMENT names; sorted!", reference).is_correct


def test_grade_marks_an_ungradable_reference() -> None:
    grade = grade_explanation("anything", "the and of")

    assert grade.is_gradable is False
    assert grade.is_correct is False
    assert grade.key_term_count == 0


def test_threshold_is_configurable() -> None:
    grade = grade_explanation(
        "Filters customers", "Filters customers by country and status",
        threshold=0.4,
    )

    assert grade.threshold == 0.4
    assert grade.is_correct is True


def test_default_threshold_is_half() -> None:
    assert DEFAULT_THRESHOLD == 0.5
    assert ExplanationGrade(True, 1.0, (), ()).threshold == 0.5
