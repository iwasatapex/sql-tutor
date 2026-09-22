from pathlib import Path

from sql_tutor.config import Settings
from sql_tutor.web import TutorWebApp


def test_exercise_payload_contains_schema(tmp_path: Path) -> None:
    settings = Settings(data_dir=Path("data"), database_path=tmp_path / "progress.db")
    app = TutorWebApp(settings)
    try:
        state = app.state()
        assert state["exercise"]["schema"]
        assert state["exercise"]["title"]
    finally:
        app.close()


def test_topic_selection_is_exposed_and_selects_topic(tmp_path: Path) -> None:
    settings = Settings(data_dir=Path("data"), database_path=tmp_path / "progress.db")
    app = TutorWebApp(settings)
    try:
        state = app.state()
        assert "WINDOW FUNCTIONS" in state["topics"]

        selected = app.choose_topic("SELECT")
        assert selected["selected_topic"] == "SELECT"
        assert selected["exercise"]["concept"].upper() == "SELECT"

        adaptive = app.choose_topic(None)
        assert adaptive["selected_topic"] is None
    finally:
        app.close()
