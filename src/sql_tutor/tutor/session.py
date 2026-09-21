import logging
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, replace

from sql_tutor.exercises.models import Exercise
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector, TopicProgress
from sql_tutor.sql.engine import QueryResult, SQLEngine
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.hints import Hint
from sql_tutor.tutor.explanation import ExplanationGrade, grade_explanation
from sql_tutor.tutor.orchestrator import TutorFeedback, TutorOrchestrator
from sql_tutor.tutor.prediction import format_query_result, prediction_matches
from sql_tutor.exercises.generator import ExerciseGenerator, ExerciseGenerationError
from sql_tutor.exercises.models import ExerciseDifficulty
from sql_tutor.exercises.sqlite_compat import normalize_difficulty_label
from sql_tutor.sql.safety import UnsafeQueryError

logger = logging.getLogger(__name__)

_AUTO_HINT_AFTER_FAILURES = 2
_MAX_HINT_LEVEL = 3


class NoActiveExerciseError(RuntimeError):
    """Raised when an action needs an exercise but none is active."""


class NoExercisesAvailableError(NoActiveExerciseError, ValueError):
    """Raised by ``start()``/``next()`` when the selector has nothing left.

    Also a ``ValueError`` because the pre-v2 session raised that for an
    empty exercise list.
    """


class ExerciseSetupError(RuntimeError):
    """Raised when an exercise's database cannot be built."""


class QuestionTypeMismatchError(ValueError):
    """Raised when an answer endpoint does not match the active exercise."""


@dataclass(frozen=True)
class SessionState:
    """Snapshot of the active exercise (pre-v2 session API)."""

    current_exercise: Exercise
    attempts: int
    last_feedback: TutorFeedback | None = None


@dataclass(frozen=True)
class SubmissionOutcome:
    feedback: TutorFeedback
    failed_attempts: int
    exercise_completed: bool

    # The pre-v2 ``submit`` returned the TutorFeedback itself. These
    # read-through properties keep that call style working.
    @property
    def is_correct(self) -> bool:
        return self.feedback.is_correct

    @property
    def message(self) -> str:
        return self.feedback.message

    @property
    def reason(self) -> str:
        return self.feedback.reason

    @property
    def hint(self) -> Hint | None:
        return self.feedback.hint

    @property
    def error(self) -> str | None:
        return self.feedback.error


@dataclass(frozen=True)
class PredictionOutcome:
    """Result of grading a Predict output answer."""

    feedback: TutorFeedback
    actual_output: str
    failed_attempts: int
    exercise_completed: bool

    @property
    def is_correct(self) -> bool:
        return self.feedback.is_correct

    @property
    def message(self) -> str:
        return self.feedback.message


@dataclass(frozen=True)
class ExplanationOutcome:
    """Result of grading an Explain SQL answer."""

    feedback: TutorFeedback
    grade: ExplanationGrade
    reference_explanation: str
    failed_attempts: int
    exercise_completed: bool

    @property
    def is_correct(self) -> bool:
        return self.feedback.is_correct

    @property
    def message(self) -> str:
        return self.feedback.message


class LearningSession:
    """One learner working through exercises.

    Selects exercises adaptively, builds a fresh database per exercise from
    its ``setup_sql`` *before* the learner can query it, evaluates
    submissions, escalates hints, and records every attempt.

    Two construction forms are accepted:

    * v2: ``LearningSession(repository, selector, progress_store[, orchestrator])``
    * pre-v2 (positional): ``LearningSession(exercises, engine, progress_store
      [, selector[, tutor]])``. ``exercises`` is any iterable of ``Exercise``.
      The caller's ``engine`` is used only for exercises that ship no
      ``setup_sql`` (the old "bring your own data" contract). Exercises with
      ``setup_sql`` always get their own isolated database, and the caller's
      engine is never modified or closed by the session.
    """

    def __init__(
        self,
        repository: ExerciseRepository | Iterable[Exercise],
        selector: ExerciseSelector | SQLEngine,
        progress_store: ProgressStore,
        orchestrator: TutorOrchestrator | ExerciseSelector | None = None,
        tutor: TutorOrchestrator | None = None,
        generator: ExerciseGenerator | None = None,
    ) -> None:
        self._external_engine: SQLEngine | None = None

        if isinstance(selector, SQLEngine):
            # Pre-v2 form: (exercises, engine, progress_store, selector, tutor)
            self._external_engine = selector

            if not isinstance(repository, ExerciseRepository):
                repository = ExerciseRepository(repository)

            legacy_selector = (
                orchestrator if isinstance(orchestrator, ExerciseSelector)
                else None
            )
            selector = legacy_selector or ExerciseSelector(
                Curriculum.default(), repository
            )
            orchestrator = tutor
        elif isinstance(orchestrator, ExerciseSelector):
            raise TypeError(
                "orchestrator must be a TutorOrchestrator, "
                "got an ExerciseSelector"
            )
        else:
            orchestrator = orchestrator or tutor

        if not isinstance(repository, ExerciseRepository):
            raise TypeError(
                "repository must be an ExerciseRepository "
                "(or an iterable of Exercise with an SQLEngine)"
            )

        self.repository = repository
        self.selector = selector
        self.progress_store = progress_store
        self.orchestrator = orchestrator or TutorOrchestrator(progress_store)
        self.generator = generator

        self._skipped: set[str] = set()
        self._engine: SQLEngine | None = None
        self._owns_engine = False
        self.current: Exercise | None = None
        self.failed_attempts = 0
        self.hints_used = 0
        self._attempts = 0
        self._last_feedback: TutorFeedback | None = None
        self.selected_concept: str | None = None
        self.selected_difficulty: ExerciseDifficulty | None = None
        self.selected_question_type: str = "write"

    @property
    def state(self) -> SessionState | None:
        if self.current is None:
            return None

        return SessionState(
            current_exercise=self.current,
            attempts=self._attempts,
            last_feedback=self._last_feedback,
        )

    def start(self) -> SessionState:
        """Select the first exercise and return its state.

        Raises ``NoExercisesAvailableError`` if nothing can be selected.
        """
        exercise = self.next_exercise()

        if exercise is None:
            raise NoExercisesAvailableError("No exercises available")

        state = self.state
        assert state is not None
        return state

    def next(self) -> SessionState:
        """Move on to another exercise (pre-v2 ``:next`` behavior).

        An unsolved current exercise is skipped for the rest of the session,
        so the selector cannot hand it straight back.
        """
        if self.current is not None:
            self._skipped.add(self.current.exercise_id)

        return self.start()

    def set_topic(self, concept: str | None) -> None:
        """Set an explicit practice topic, or None for adaptive practice."""
        if concept is None or not concept.strip():
            self.selected_concept = None
            return
        topic = self.selector.curriculum.get_topic(concept)
        if topic is None:
            raise ValueError(f"Unknown curriculum topic: {concept}")
        self.selected_concept = topic.title

    def set_difficulty(self, difficulty: ExerciseDifficulty | str | None) -> None:
        """Pin practice to one difficulty, or None for adaptive difficulty."""
        if difficulty is None:
            self.selected_difficulty = None
            return
        if isinstance(difficulty, ExerciseDifficulty):
            self.selected_difficulty = difficulty
            return
        normalized = normalize_difficulty_label(difficulty)
        if normalized is None:
            raise ValueError(
                f"Unknown difficulty: {difficulty!r}. "
                "Use beginner, intermediate, advanced, or adaptive."
            )
        self.selected_difficulty = ExerciseDifficulty(normalized)

    def set_question_type(self, question_type: str | None) -> None:
        """Set how the learner practices; all four question types are supported."""
        normalized = (question_type or "write").strip().lower()
        if normalized in {"write", "write sql", "write_sql"}:
            self.selected_question_type = "write"
            return
        if normalized in {"debug", "debug sql", "debug_sql"}:
            self.selected_question_type = "debug"
            return
        if normalized in {"predict", "predict output", "predict_output"}:
            self.selected_question_type = "predict"
            return
        if normalized in {"explain", "explain sql", "explain_sql"}:
            self.selected_question_type = "explain"
            return
        raise ValueError(
            f"Unsupported question type: {question_type!r}. "
            "Use 'write', 'debug', 'predict', or 'explain'."
        )

    def next_exercise(self) -> Exercise | None:
        self._close_engine()
        self.current = None

        attempts = self.progress_store.get_all_attempts()
        exercise = None

        if self.generator is not None:
            if self.selected_concept is not None:
                concept, adaptive_difficulty = (
                    self.selector.generation_target_for_concept(
                        self.selected_concept, attempts
                    )
                )
            else:
                concept, adaptive_difficulty = self.selector.generation_target(
                    attempts
                )
            difficulty = self.selected_difficulty or adaptive_difficulty
            try:
                exercise = self.generator.generate(
                    concept, difficulty, self.selected_question_type
                )
                if self.repository.get(exercise.exercise_id) is None:
                    self.repository.add(exercise)
            except ExerciseGenerationError as error:
                logger.warning("Generated exercise unavailable: %s", error)

        if exercise is None:
            exercise = self.selector.select_next(
                attempts,
                exclude_ids=self._skipped,
                concept=self.selected_concept,
                difficulty=self.selected_difficulty,
                question_type=self.selected_question_type,
            )

        self.failed_attempts = 0
        self.hints_used = 0
        self._attempts = 0
        self._last_feedback = None

        if exercise is not None:
            self._engine, self._owns_engine = self._provision(exercise)
            self.current = exercise

        return exercise

    def submit(
        self,
        student_query: str,
        hint_level: int | None = None,
    ) -> SubmissionOutcome:
        exercise, engine = self._require_active()
        self._require_question_type(exercise, "write", "debug")

        feedback = self.orchestrator.submit_query(
            exercise,
            engine,
            student_query,
            hint_level=hint_level or self.hints_used or None,
            ignore_row_order=_ignore_row_order(exercise),
        )
        self._attempts += 1

        if feedback.is_correct:
            self._last_feedback = feedback
            return SubmissionOutcome(
                feedback=feedback,
                failed_attempts=self.failed_attempts,
                exercise_completed=True,
            )

        self.failed_attempts += 1

        if (
            feedback.hint is None
            and feedback.error is None
            and self.failed_attempts >= _AUTO_HINT_AFTER_FAILURES
        ):
            feedback = replace(
                feedback,
                hint=self.orchestrator._get_hint(
                    exercise,
                    min(self.failed_attempts - 1, _MAX_HINT_LEVEL),
                    student_query,
                ),
            )

        self._last_feedback = feedback

        return SubmissionOutcome(
            feedback=feedback,
            failed_attempts=self.failed_attempts,
            exercise_completed=False,
        )

    def expected_output(self) -> str:
        """Pipe-separated output of the current exercise's reference query."""
        exercise, engine = self._require_active()

        return format_query_result(engine.execute_query(exercise.expected_query))

    def submit_prediction(self, prediction: str) -> PredictionOutcome:
        """Grade a predicted result for the active exercise.

        Nothing is run on the learner's behalf: the reference query is
        authored content, so executing it against the exercise database is
        how the real output is produced. The attempt is recorded like any
        other answer so topic progress and mastery stay accurate.
        """
        if not str(prediction or "").strip():
            raise ValueError("Prediction cannot be empty")

        exercise, _ = self._require_active()
        self._require_question_type(exercise, "predict")
        actual_output = self.expected_output()
        is_correct = prediction_matches(prediction, actual_output)
        feedback = TutorFeedback(
            is_correct=is_correct,
            message=(
                "Correct! Your prediction matched the query output."
                if is_correct
                else "Not quite. Compare your prediction with the actual output."
            ),
            reason=(
                ""
                if is_correct
                else "Read each clause of the query again and check the "
                "returned columns and rows."
            ),
        )

        self._attempts += 1

        if not is_correct:
            self.failed_attempts += 1

        self._last_feedback = feedback
        self._record_attempt(
            exercise, prediction, is_correct, self.hints_used or None
        )

        return PredictionOutcome(
            feedback=feedback,
            actual_output=actual_output,
            failed_attempts=self.failed_attempts,
            exercise_completed=is_correct,
        )

    def submit_explanation(self, explanation: str) -> ExplanationOutcome:
        """Grade a natural-language explanation of the active exercise.

        The answer is compared with the exercise's reference explanation
        and the attempt is recorded like any other answer, so explain
        practice also feeds topic progress and mastery.
        """
        if not str(explanation or "").strip():
            raise ValueError("Explanation cannot be empty")

        exercise, _ = self._require_active()
        self._require_question_type(exercise, "explain")
        reference = exercise.reference_explanation
        grade = grade_explanation(explanation, reference)

        if not grade.is_gradable:
            raise ValueError(
                f"Exercise '{exercise.exercise_id}' has no reference "
                "explanation to grade against"
            )

        feedback = TutorFeedback(
            is_correct=grade.is_correct,
            message=(
                "Correct! Your explanation covered the key ideas."
                if grade.is_correct
                else "Not quite. Your explanation missed some key ideas."
            ),
            reason=(
                ""
                if grade.is_correct
                else f"Missing ideas: {grade.missing_terms}"
            ),
        )

        self._attempts += 1

        if not grade.is_correct:
            self.failed_attempts += 1

        self._last_feedback = feedback
        self._record_attempt(
            exercise, explanation, grade.is_correct, self.hints_used or None
        )

        return ExplanationOutcome(
            feedback=feedback,
            grade=grade,
            reference_explanation=reference,
            failed_attempts=self.failed_attempts,
            exercise_completed=grade.is_correct,
        )

    def request_hint(self) -> Hint:
        exercise, _ = self._require_active()
        self.hints_used = min(self.hints_used + 1, _MAX_HINT_LEVEL)

        return self.orchestrator._get_hint(exercise, self.hints_used)

    def preview(self, student_query: str) -> QueryResult | None:
        """Run a query for display only; returns None if it cannot run."""
        _, engine = self._require_active()

        try:
            return engine.execute_query(student_query)
        except Exception:
            return None

    def skip(self) -> None:
        exercise, _ = self._require_active()
        self._skipped.add(exercise.exercise_id)

    def topic_progress(self) -> tuple[TopicProgress, ...]:
        return self.selector.topic_progress(
            self.progress_store.get_all_attempts()
        )

    def close(self) -> None:
        self._close_engine()
        self.current = None

    def _record_attempt(
        self,
        exercise: Exercise,
        answer: str,
        is_correct: bool,
        hint_level: int | None,
    ) -> None:
        """Log one attempt, whatever question type produced the answer."""
        self.progress_store.record_attempt(
            exercise_id=exercise.exercise_id,
            student_query=answer,
            is_correct=is_correct,
            hint_level=hint_level,
        )

    def _provision(self, exercise: Exercise) -> tuple[SQLEngine, bool]:
        """Return ``(engine, owned)`` with the exercise's data loaded.

        Raises ``ExerciseSetupError`` rather than handing back an empty
        database that would only fail later with "no such table".
        """
        if exercise.setup_sql:
            engine = SQLEngine()

            try:
                engine.execute_setup(list(exercise.setup_sql))
            except sqlite3.Error as error:
                engine.close()
                raise ExerciseSetupError(
                    f"Could not build database for exercise "
                    f"'{exercise.exercise_id}': {error}"
                ) from error
            except (UnsafeQueryError, ValueError) as error:
                engine.close()
                raise ExerciseSetupError(
                    f"Could not build database for exercise "
                    f"'{exercise.exercise_id}': {error}"
                ) from error

            return engine, True

        if self._external_engine is not None:
            logger.info(
                "Exercise %s has no setup_sql; using the caller's engine",
                exercise.exercise_id,
            )
            return self._external_engine, False

        raise ExerciseSetupError(
            f"Exercise '{exercise.exercise_id}' has no setup_sql, so its "
            "tables and data cannot be created"
        )

    def _require_active(self) -> tuple[Exercise, SQLEngine]:
        if self.current is None or self._engine is None:
            raise NoActiveExerciseError("No active exercise")

        return self.current, self._engine

    @staticmethod
    def _require_question_type(exercise: Exercise, *allowed: str) -> None:
        if exercise.question_type.value not in allowed:
            endpoint = "/api/submit" if set(allowed) == {"write", "debug"} else (
                "/api/predict" if allowed == ("predict",) else "/api/explain"
            )
            expected = " or ".join(allowed)
            raise QuestionTypeMismatchError(
                f"{endpoint} accepts {expected} exercises, but the active "
                f"exercise is {exercise.question_type.value}"
            )

    def _close_engine(self) -> None:
        if self._engine is not None and self._owns_engine:
            self._engine.close()

        self._engine = None
        self._owns_engine = False


def _ignore_row_order(exercise: Exercise) -> bool:
    """Row order only matters when the reference query sorts."""
    return "ORDER BY" not in exercise.expected_query.upper()
