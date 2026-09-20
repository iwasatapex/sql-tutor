import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    # src/sql_tutor/config.py -> repository root / data
    return Path(__file__).resolve().parents[2] / "data"


def _default_database_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "sql-tutor" / "progress.db"


OLLAMA_MODELS: tuple[tuple[str, str], ...] = (
    ("Granite", "granite4.1:3b-q6_K"),
    ("Gemma", "batiai/gemma4-e4b:q4"),
    ("Ornith", "ornith-1.5-9b-iq4-xs:latest"),
)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    llm_provider: str = "mock"
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_timeout_seconds: float = 120.0

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "Settings":
        env = os.environ if environ is None else environ

        return cls(
            data_dir=Path(env["SQL_TUTOR_DATA_DIR"])
            if "SQL_TUTOR_DATA_DIR" in env
            else _default_data_dir(),
            database_path=Path(env["SQL_TUTOR_DB"])
            if "SQL_TUTOR_DB" in env
            else _default_database_path(),
            llm_provider=env.get("SQL_TUTOR_LLM_PROVIDER", "mock").lower(),
            llm_model=env.get("SQL_TUTOR_LLM_MODEL"),
            llm_base_url=env.get("SQL_TUTOR_LLM_BASE_URL"),
            llm_api_key=env.get("SQL_TUTOR_LLM_API_KEY"),
            llm_timeout_seconds=float(
                env.get("SQL_TUTOR_LLM_TIMEOUT", "120")
            ),
        )
