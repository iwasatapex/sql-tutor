from dataclasses import dataclass

from sql_tutor.exercises.models import Exercise
from sql_tutor.learning.selector import ExerciseSelector, ExerciseSelection
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.orchestrator import TutorFeedback, TutorOrchestrator


@dataclass(frozen=True)
class SessionState:
    current_exercise: Exercise
    attempts: int
    last_feedback: TutorFeedback | None = None


class LearningSession:
    def __init__(
        self,
        exercises: tuple[Exercise, ...],
        engine: SQLEngine,
        progress_store: ProgressStore,
        selector: ExerciseSelector | None = None,
        tutor: TutorOrchestrator | None = None,
    ) -> None:
        self.exercises = exercises
        self.engine = engine
        self.progress_store = progress_store
        self.selector = selector or ExerciseSelector()
        self.tutor = tutor or TutorOrchestrator(progress_store=progress_store)
        self._state: SessionState | None = None
        self._prepared = False

    @property
    def state(self) -> SessionState | None:
        return self._state

    def start(self) -> SessionState:
        if not self._prepared:
            statements = [statement for exercise in self.exercises for statement in exercise.setup_statements]
            if statements:
                self.engine.execute_setup(statements)
            self._prepared = True
        selection = self.selector.select(self.exercises, self.progress_store)
        self._state = SessionState(current_exercise=selection.exercise, attempts=0)
        return self._state

    def submit(self, student_query: str, hint_level: int | None = None) -> TutorFeedback:
        if self._state is None:
            raise RuntimeError("Session has not started")
        feedback = self.tutor.submit_query(
            exercise=self._state.current_exercise,
            engine=self.engine,
            student_query=student_query,
            hint_level=hint_level,
        )
        self._state = SessionState(
            current_exercise=self._state.current_exercise,
            attempts=self._state.attempts + 1,
            last_feedback=feedback,
        )
        return feedback

    def next(self) -> SessionState:
        return self.start()
