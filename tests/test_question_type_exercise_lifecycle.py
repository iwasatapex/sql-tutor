"""End-to-end regressions for the bundled Debug and Predict exercises."""

from pathlib import Path

import pytest

from sql_tutor.config import Settings
from sql_tutor.exercises.models import QuestionType
from sql_tutor.exercises.repository import ExerciseRepository
from sql_tutor.tutor.session import QuestionTypeMismatchError
from sql_tutor.web import TutorWebApp, _exercise_payload

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_debug_filtered_employees_is_provisioned_displayed_and_graded(
    tmp_path: Path,
) -> None:
    app = TutorWebApp(Settings(data_dir=DATA_DIR, database_path=tmp_path / "p.db"))
    try:
        state = app.choose_question_type("debug")
        exercise = app.session.current
        assert exercise is not None
        assert exercise.exercise_id == "debug-filtered-employees"
        assert exercise.question_type == QuestionType.DEBUG
        assert state["exercise"]["broken_query"] == (
            "SELECT name, salary FROM employees WHERE department_id = 2;"
        )

        result = app.submit(
            "SELECT name, salary FROM employees WHERE department_id = 1;"
        )
        assert result["feedback"]["is_correct"] is True
    finally:
        app.close()


def test_predict_department_names_uses_company_data_and_type_routing(
    tmp_path: Path,
) -> None:
    app = TutorWebApp(Settings(data_dir=DATA_DIR, database_path=tmp_path / "p.db"))
    try:
        app.choose_question_type("predict")
        exercise = app.session.current
        assert exercise is not None
        assert exercise.exercise_id == "predict-department-names"
        assert exercise.question_type == QuestionType.PREDICT
        assert _exercise_payload(exercise)["query"] == (
            "SELECT name FROM departments ORDER BY name;"
        )
        assert app.session.expected_output() == (
            "name\nEngineering\nLegal\nMarketing\nSales"
        )

        with pytest.raises(QuestionTypeMismatchError, match="/api/submit"):
            app.submit("SELECT name FROM departments ORDER BY name;")

        result = app.predict("name\nEngineering\nLegal\nMarketing\nSales")
        assert result["feedback"]["is_correct"] is True
    finally:
        app.close()


def test_company_dataset_builds_setup_for_all_tables_and_limits_display_schema() -> None:
    repository = ExerciseRepository.from_directory(DATA_DIR)
    debug = repository.get("debug-filtered-employees")
    predict = repository.get("predict-department-names")

    assert debug is not None and predict is not None
    assert tuple(table.name for table in debug.schema) == ("employees",)
    assert tuple(table.name for table in predict.schema) == ("departments",)
    assert any(statement.startswith("CREATE TABLE employees") for statement in debug.setup_sql)
    assert any(statement.startswith("CREATE TABLE departments") for statement in predict.setup_sql)
