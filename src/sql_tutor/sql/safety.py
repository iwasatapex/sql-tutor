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


def validate_read_only_query(query: str) -> None:
    """Validate that a query is a single read-only SQL statement."""
    normalized = query.strip()

    if not normalized:
        raise UnsafeQueryError("Query cannot be empty")

    without_trailing_semicolon = normalized.rstrip(";").strip()

    if ";" in without_trailing_semicolon:
        raise UnsafeQueryError("Multiple SQL statements are not allowed")

    if "--" in normalized or "/*" in normalized or "*/" in normalized:
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

    upper_query = normalized.upper()

    for forbidden_keyword in _FORBIDDEN_KEYWORDS:
        if re.search(
            rf"\b{forbidden_keyword}\b",
            upper_query,
        ):
            raise UnsafeQueryError(
                f"Forbidden SQL keyword: {forbidden_keyword}"
            )
