from sql_tutor.learning.mastery import (
    MasteryLevel,
    MasteryTracker,
)


def test_no_attempts_returns_novice() -> None:
    tracker = MasteryTracker()

    result = tracker.calculate(())

    assert result.level == MasteryLevel.NOVICE
    assert result.accuracy == 0.0


def test_all_correct_returns_mastered() -> None:
    tracker = MasteryTracker()

    result = tracker.calculate((True, True, True, True, True))

    assert result.level == MasteryLevel.MASTERED
    assert result.accuracy == 1.0


def test_mostly_correct_returns_proficient() -> None:
    tracker = MasteryTracker()

    result = tracker.calculate((True, True, True, False))

    assert result.level == MasteryLevel.PROFICIENT
    assert result.accuracy == 0.75


def test_mixed_results_returns_developing() -> None:
    tracker = MasteryTracker()

    result = tracker.calculate((True, False, False, True))

    assert result.level == MasteryLevel.DEVELOPING
    assert result.accuracy == 0.5


def test_low_accuracy_returns_novice() -> None:
    tracker = MasteryTracker()

    result = tracker.calculate((False, False, True, False))

    assert result.level == MasteryLevel.NOVICE
    assert result.accuracy == 0.25