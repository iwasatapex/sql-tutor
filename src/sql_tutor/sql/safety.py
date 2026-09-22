import re


class UnsafeQueryError(ValueError):
    """Raised when a SQL query violates the safety policy."""


_FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
}


def _strip_quoted_sql_segments(query: str) -> str:
    """Replace string literals and quoted identifiers with spaces."""
    sanitized: list[str] = []
    index = 0
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    in_bracket_ident = False

    while index < len(query):
        char = query[index]
        next_char = query[index + 1] if index + 1 < len(query) else ""

        if in_single_quote:
            if char == "'" and next_char == "'":
                sanitized.extend("  ")
                index += 2
                continue
            if char == "'":
                in_single_quote = False
            sanitized.append(" ")
            index += 1
            continue

        if in_double_quote:
            if char == '"' and next_char == '"':
                sanitized.extend("  ")
                index += 2
                continue
            if char == '"':
                in_double_quote = False
            sanitized.append(" ")
            index += 1
            continue

        if in_backtick:
            if char == "`" and next_char == "`":
                sanitized.extend("  ")
                index += 2
                continue
            if char == "`":
                in_backtick = False
            sanitized.append(" ")
            index += 1
            continue

        if in_bracket_ident:
            if char == "]" and next_char == "]":
                sanitized.extend("  ")
                index += 2
                continue
            if char == "]":
                in_bracket_ident = False
            sanitized.append(" ")
            index += 1
            continue

        if char == "'":
            in_single_quote = True
            sanitized.append(" ")
            index += 1
            continue

        if char == '"':
            in_double_quote = True
            sanitized.append(" ")
            index += 1
            continue

        if char == "`":
            in_backtick = True
            sanitized.append(" ")
            index += 1
            continue

        if char == "[":
            in_bracket_ident = True
            sanitized.append(" ")
            index += 1
            continue

        sanitized.append(char)
        index += 1

    if (
        in_single_quote
        or in_double_quote
        or in_backtick
        or in_bracket_ident
    ):
        raise UnsafeQueryError("Query contains an unterminated quoted segment")

    return "".join(sanitized)


def validate_read_only_query(query: str) -> None:
    """Validate that a query is a single read-only SQL statement."""
    normalized = query.strip()

    if not normalized:
        raise UnsafeQueryError("Query cannot be empty")

    public_sql = _strip_quoted_sql_segments(normalized)
    without_trailing_semicolon = public_sql.rstrip(";").strip()

    if ";" in without_trailing_semicolon:
        raise UnsafeQueryError("Multiple SQL statements are not allowed")

    if "--" in public_sql or "/*" in public_sql or "*/" in public_sql:
        raise UnsafeQueryError("SQL comments are not allowed")

    first_keyword = re.match(
        r"^([A-Za-z]+)",
        normalized,
    )

    if first_keyword is None:
        raise UnsafeQueryError("Query must begin with a SQL keyword")

    keyword = first_keyword.group(1).upper()

    if keyword not in {"SELECT", "WITH"}:
        raise UnsafeQueryError(
            "Only SELECT and WITH queries are allowed"
        )

    for forbidden_keyword in _FORBIDDEN_KEYWORDS:
        if re.search(
            rf"\b{re.escape(forbidden_keyword)}\b",
            public_sql,
            flags=re.IGNORECASE,
        ):
            raise UnsafeQueryError(
                f"Forbidden SQL keyword: {forbidden_keyword}"
            )
