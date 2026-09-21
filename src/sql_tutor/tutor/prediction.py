"""Grading helpers for the Predict output question type.

A predict exercise shows the learner a reference query and asks for its
result. The answer is written as plain text: one line per result row with
the columns separated by ``|``, the first line being the column names.
Grading compares that text with the query's real output line by line, so
it is deterministic and fully offline.
"""

import re

from sql_tutor.sql.engine import QueryResult

#: How ``None`` is rendered in the pipe-separated answer format.
NULL_DISPLAY = ""

#: Column separator used by the answer format and the UI placeholder.
COLUMN_SEPARATOR = " | "

_SEPARATOR_SPACING = re.compile(r"\s*\|\s*")


def format_query_result(result: QueryResult) -> str:
    """Render a query result as the pipe-separated text learners predict."""
    lines = [COLUMN_SEPARATOR.join(str(column) for column in result.columns)]

    for row in result.rows:
        lines.append(
            COLUMN_SEPARATOR.join(_cell(value) for value in row).rstrip()
        )

    return "\n".join(lines)


def prediction_matches(prediction: str, actual_output: str) -> bool:
    """Compare a prediction with the real output, ignoring blank lines.

    Lines are compared after trimming surrounding whitespace and the
    optional spaces around each ``|`` separator, so ``a|b`` and ``a | b``
    are the same answer. Values inside a column are compared exactly.
    """
    return _answer_lines(prediction) == _answer_lines(actual_output)


def _cell(value: object) -> str:
    return NULL_DISPLAY if value is None else str(value)


def _answer_lines(text: object) -> list[str]:
    lines = []

    for raw_line in str(text or "").splitlines():
        line = _SEPARATOR_SPACING.sub("|", raw_line.strip())

        if line:
            lines.append(line)

    return lines
