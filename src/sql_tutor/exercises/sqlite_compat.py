"""Utilities for keeping LLM-generated SQL SQLite-compatible.

Models trained mostly on MySQL/Postgres/T-SQL text frequently emit
statements or functions that SQLite does not provide (``ROW_COUNT()``,
``NOW()``, ``DATE_FORMAT()``, ...). Running such SQL fails late with
errors like ``no such function: ROW_COUNT``; helpers here catch those
problems early, with clear messages the generator feeds back to the
model, and reassemble common LLM formatting mistakes (split multi-row
``INSERT`` fragments) before validation runs.
"""

from __future__ import annotations

import re
from typing import Any

# Functions that do NOT exist in SQLite but that LLMs regularly emit
# because they are common in MySQL / Postgres / T-SQL / Oracle.
_NON_SQLITE_FUNCTIONS: dict[str, str] = {
    # Affected-row helpers (MySQL / T-SQL).
    "ROW_COUNT": "SQLite has no ROW_COUNT(); use changes() instead",
    "FOUND_ROWS": "SQLite has no FOUND_ROWS()",
    "LAST_INSERT_ID": "SQLite has no LAST_INSERT_ID(); use last_insert_rowid()",
    "@@ROWCOUNT": "SQLite has no @@ROWCOUNT; use changes() instead",
    # Current date/time helpers from other dialects.
    "NOW": "SQLite has no NOW(); use CURRENT_TIMESTAMP or datetime('now')",
    "CURDATE": "SQLite has no CURDATE(); use date('now') instead",
    "CURTIME": "SQLite has no CURTIME(); use time('now') instead",
    "SYSDATE": "SQLite has no SYSDATE; use CURRENT_TIMESTAMP instead",
    "GETDATE": "SQLite has no GETDATE(); use CURRENT_TIMESTAMP instead",
    "SYSDATETIME": "SQLite has no SYSDATETIME; use CURRENT_TIMESTAMP",
    "CURRENT_TIME_STAMP": "SQLite spells it CURRENT_TIMESTAMP",
    # Date formatting / parsing helpers from other dialects.
    "DATE_FORMAT": "SQLite has no DATE_FORMAT(); use strftime() instead",
    "STR_TO_DATE": "SQLite has no STR_TO_DATE(); use date()/strftime()",
    "TO_CHAR": "SQLite has no TO_CHAR(); use CAST() or printf() instead",
    "TO_DATE": "SQLite has no TO_DATE(); use date()/datetime() instead",
    "TO_NUMBER": "SQLite has no TO_NUMBER(); use CAST() instead",
    "DATEADD": "SQLite has no DATEADD(); use date(..., '+N days') modifiers",
    "DATEPART": "SQLite has no DATEPART(); use strftime() instead",
    "DATENAME": "SQLite has no DATENAME(); use strftime() instead",
    # Conditional / null helpers from other dialects (SQLite uses
    # CASE, COALESCE, IFNULL, and IIF).
    "NVL": "SQLite has no NVL(); use IFNULL() or COALESCE() instead",
    "NVL2": "SQLite has no NVL2(); use CASE or IIF() instead",
    "ISNULL": "SQLite has no ISNULL() function; use IFNULL() or IS NULL",
    "IF": "SQLite has no IF() function; use IIF() or CASE instead",
    "DECODE": "SQLite has no DECODE(); use CASE instead",
    # String helpers from other dialects.
    "SUBSTRING_INDEX": "SQLite has no SUBSTRING_INDEX(); use substr()/instr()",
    "CHARINDEX": "SQLite has no CHARINDEX(); use instr() instead",
    "STUFF": "SQLite has no STUFF(); use substr() concatenation instead",
    "CONCAT_WS": "SQLite has no CONCAT_WS(); use || concatenation instead",
    "STRING_AGG": "SQLite has no STRING_AGG(); use group_concat() instead",
    "LISTAGG": "SQLite has no LISTAGG(); use group_concat() instead",
    "REVERSE": "SQLite has no REVERSE(); use a recursive CTE instead",
    # Oracle / Postgres helpers.
    "DUAL": "SQLite has no DUAL table; SELECT without FROM instead",
    "ROWNUM": "SQLite has no ROWNUM; use ROW_NUMBER() OVER (...) or LIMIT",
    "NEXTVAL": "SQLite has no sequence NEXTVAL; use INTEGER PRIMARY KEY",
    "GENERATE_SERIES": "SQLite has no generate_series(); use recursive CTE",
    # MySQL grouping helper.
    "WITH_ROLLUP": "SQLite does not support WITH ROLLUP",
}

_FUNCTION_CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_AT_VARIABLE_PATTERN = re.compile(r"(@@[A-Za-z_][A-Za-z0-9_]*)")
_QUOTED_LITERAL_PATTERN = re.compile(r"'(?:[^']|'')*'")


def _strip_string_literals(sql: str) -> str:
    """Remove single-quoted literals so scans skip text data."""
    return _QUOTED_LITERAL_PATTERN.sub("''", sql)


def find_unsupported_functions(sql: str) -> tuple[str, ...]:
    """Return sorted names of non-SQLite functions called in ``sql``.

    String literals are ignored, so ``SELECT 'NOW()'`` is fine. Matching
    is case-insensitive (``row_count()``, ``ROW_COUNT()``) because SQLite
    function names are case-insensitive too.
    """
    cleaned = _strip_string_literals(sql)
    found: set[str] = set()
    for match in _FUNCTION_CALL_PATTERN.finditer(cleaned.upper()):
        name = match.group(1)
        if name in _NON_SQLITE_FUNCTIONS:
            found.add(name)
    for match in _AT_VARIABLE_PATTERN.finditer(cleaned.upper()):
        if match.group(1) in _NON_SQLITE_FUNCTIONS:
            found.add(match.group(1))
    return tuple(sorted(found))


def unsupported_function_message(name: str) -> str:
    """Human-readable guidance for one unsupported function name."""
    return _NON_SQLITE_FUNCTIONS.get(
        name.upper(), f"SQLite does not support {name}()"
    )


def sqlite_compatibility_errors(sql: str) -> tuple[str, ...]:
    """Validate that one SQL statement only uses SQLite functions."""
    return tuple(
        f"Unsupported function {name}(): {unsupported_function_message(name)}"
        for name in find_unsupported_functions(sql)
    )


_SETUP_HEAD_PATTERN = re.compile(
    r"^\s*(CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?|INSERT\s+INTO)\b",
    re.IGNORECASE,
)

_INSERT_VALUES_TAIL_PATTERN = re.compile(
    r"^\s*(\([^()]*\)[\s;,]*)+$", re.DOTALL
)


def normalize_setup_statements(raw: Any) -> tuple[str, ...] | None:
    """Reassemble ``setup_sql`` into one complete statement per string.

    LLMs frequently split a multi-row insert across strings, e.g.::

        ["INSERT INTO t VALUES", "(1, 'a'),", "(2, 'b');"]

    or emit a single script with several statements. This joins
    value-only fragments (``(1, 'a'),``) back onto the preceding
    ``INSERT INTO ...`` line and splits stray multi-statement strings, so
    downstream validation sees complete statements. Returns ``None`` when
    the payload is not a list/tuple of strings at all.
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)) or not all(
        isinstance(item, str) for item in raw
    ):
        return None

    joined: list[str] = []
    for item in raw:
        text = item.strip()
        if not text:
            continue
        if _SETUP_HEAD_PATTERN.match(text):
            joined.append(text)
        elif joined and _INSERT_VALUES_TAIL_PATTERN.match(text):
            joined[-1] = f"{joined[-1].rstrip()} {text}".strip()
        else:
            joined.append(text)

    statements: list[str] = []
    buffer = ""
    depth = 0
    in_string = False
    for chunk in joined:
        for char in chunk:
            if char == "'":
                in_string = not in_string
                buffer += char
            elif in_string:
                buffer += char
            elif char == "(":
                depth += 1
                buffer += char
            elif char == ")":
                depth = max(0, depth - 1)
                buffer += char
            elif char == ";" and depth == 0:
                buffer += char
                text = buffer.strip()
                if text:
                    statements.append(text)
                buffer = ""
            else:
                buffer += char
        if buffer.strip() and (depth > 0 or in_string):
            buffer += "\n"
        elif buffer.strip():
            text = buffer.strip()
            if text:
                statements.append(text)
            buffer = ""
    tail = buffer.strip()
    if tail:
        statements.append(tail)
    return tuple(statements)


_DIFFICULTY_ALIASES = {
    "beginner": "beginner",
    "easy": "beginner",
    "novice": "beginner",
    "intermediate": "intermediate",
    "medium": "intermediate",
    "advanced": "advanced",
    "hard": "advanced",
    "expert": "advanced",
}


def normalize_difficulty_label(value: Any) -> str | None:
    """Map ``Advanced``/``ADVANCED``/``hard`` style labels to enum values."""
    if value is None:
        return None
    return _DIFFICULTY_ALIASES.get(str(value).strip().lower())
