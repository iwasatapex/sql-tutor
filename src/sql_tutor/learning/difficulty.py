from sql_tutor.exercises.models import ExerciseDifficulty


class DifficultyAdjuster:
    _DIFFICULTIES = (
        ExerciseDifficulty.BEGINNER,
        ExerciseDifficulty.INTERMEDIATE,
        ExerciseDifficulty.ADVANCED,
    )

    def adjust(
        self,
        current: ExerciseDifficulty,
        recent_results: tuple[bool, ...],
    ) -> ExerciseDifficulty:
        if len(recent_results) >= 3 and all(recent_results[-3:]):
            return self._increase(current)

        if len(recent_results) >= 2 and not any(recent_results[-2:]):
            return self._decrease(current)

        return current

    def _increase(
        self,
        current: ExerciseDifficulty,
    ) -> ExerciseDifficulty:
        index = self._DIFFICULTIES.index(current)

        if index == len(self._DIFFICULTIES) - 1:
            return current

        return self._DIFFICULTIES[index + 1]

    def _decrease(
        self,
        current: ExerciseDifficulty,
    ) -> ExerciseDifficulty:
        index = self._DIFFICULTIES.index(current)

        if index == 0:
            return current

        return self._DIFFICULTIES[index - 1]