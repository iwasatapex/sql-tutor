from pathlib import Path

from sql_tutor.config import Settings
from sql_tutor.web import TutorWebApp, _exercise_payload


def test_exercise_payload_contains_schema(tmp_path: Path) -> None:
    settings = Settings(data_dir=Path("data"), database_path=tmp_path / "progress.db")
    app = TutorWebApp(settings)
    try:
        state = app.state()
        assert state["exercise"]["schema"]
        assert state["exercise"]["title"]
    finally:
        app.close()
