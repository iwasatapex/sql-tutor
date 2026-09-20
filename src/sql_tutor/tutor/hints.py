from dataclasses import dataclass


@dataclass(frozen=True)
class Hint:
    level: int
    message: str


class HintService:
    _HINTS: dict[str, tuple[str, ...]] = {
        "SELECT": (
            "Check which columns the exercise asks you to return.",
            "Review the SELECT clause and verify the selected columns.",
            "Compare your SELECT clause with the required output columns.",
        ),
        "WHERE": (
            "Check which rows should be included in the result.",
            "Review the condition in your WHERE clause.",
            "Verify the comparison operator and filter value.",
        ),
        "ORDER BY": (
            "Check whether the result needs a specific order.",
            "Review the columns used in ORDER BY.",
            "Verify the sorting direction and column order.",
        ),
        "JOIN": (
            "Identify the relationship between the tables.",
            "Review the columns used in your JOIN condition.",
            "Check whether the join type matches the exercise requirements.",
        ),
    }

    def get_hint(self, concept: str, level: int) -> Hint:
        if level < 1:
            raise ValueError("Hint level must be at least 1")

        hints = self._HINTS.get(
            concept.upper(),
            (
                "Review the SQL concept used in this exercise.",
                "Break the problem into smaller SQL clauses.",
                "Compare your query structure with the exercise requirements.",
            ),
        )

        index = min(level, len(hints)) - 1

        return Hint(
            level=index + 1,
            message=hints[index],
        )
