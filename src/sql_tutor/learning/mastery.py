from dataclasses import dataclass
from enum import StrEnum


class MasteryLevel(StrEnum):
    NOVICE = "novice"
    DEVELOPING = "developing"
    PROFICIENT = "proficient"
    MASTERED = "mastered"


@dataclass(frozen=True)
class MasteryResult:
    level: MasteryLevel
    accuracy: float


class MasteryTracker:
    def calculate(
        self,
        results: tuple[bool, ...],
    ) -> MasteryResult:
        if not results:
            return MasteryResult(
                level=MasteryLevel.NOVICE,
                accuracy=0.0,
            )

        accuracy = sum(results) / len(results)

        if accuracy == 1.0:
            level = MasteryLevel.MASTERED
        elif accuracy >= 0.75:
            level = MasteryLevel.PROFICIENT
        elif accuracy >= 0.5:
            level = MasteryLevel.DEVELOPING
        else:
            level = MasteryLevel.NOVICE

        return MasteryResult(
            level=level,
            accuracy=accuracy,
        )