import pytest

from sql_tutor.tutor.hints import HintService


def test_first_where_hint() -> None:
    hint = HintService().get_hint("WHERE", 1)

    assert hint.level == 1
    assert "rows" in hint.message


def test_progressive_where_hints() -> None:
    service = HintService()

    first = service.get_hint("WHERE", 1)
    second = service.get_hint("WHERE", 2)
    third = service.get_hint("WHERE", 3)

    assert first.message != second.message
    assert second.message != third.message


def test_high_hint_level_returns_final_hint() -> None:
    hint = HintService().get_hint("SELECT", 99)

    assert hint.level == 3


def test_invalid_hint_level() -> None:
    with pytest.raises(ValueError):
        HintService().get_hint("SELECT", 0)
