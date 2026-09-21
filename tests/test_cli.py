import io
from pathlib import Path

from sql_tutor.cli import format_table, main, read_query

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def scripted(*lines: str):
    remaining = iter(lines)

    def input_fn(prompt: str) -> str:
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError from None

    return input_fn


def run(tmp_path: Path, argv: list[str], *lines: str) -> str:
    out = io.StringIO()
    code = main(
        ["--db", str(tmp_path / "p.db"), "--data-dir", str(DATA_DIR), *argv],
        input_fn=scripted(*lines),
        out=out,
    )
    assert code == 0
    return out.getvalue()


def test_format_table_aligns_columns_and_truncates() -> None:
    text = format_table(("a", "bb"), [(1, None), (22, "x"), (3, "y")], max_rows=2)

    lines = text.splitlines()
    assert lines[0].startswith("a ")
    assert "NULL" in lines[2]
    assert lines[-1] == "... 1 more rows"


def test_read_query_handles_multiline_and_commands() -> None:
    assert read_query(scripted("SELECT 1", "FROM t;")) == "SELECT 1\nFROM t;"
    assert read_query(scripted(":HINT")) == ":hint"
    assert read_query(scripted("", "SELECT 1", "")) == "SELECT 1"
    assert read_query(scripted()) is None


def test_practice_session_end_to_end(tmp_path: Path) -> None:
    output = run(
        tmp_path, ["practice"],
        "SELECT id FROM employees;",
        ":hint",
        "SELECT name FROM employees;",
        ":quit",
    )

    assert "All employee names" in output
    assert "Your query returned:" in output
    assert "Hint:" in output
    assert "Correct!" in output


def test_progress_persists_between_runs(tmp_path: Path) -> None:
    run(tmp_path, ["practice"], "SELECT name FROM employees;", ":quit")

    output = run(tmp_path, ["progress"])

    assert "SELECT    1/7 solved  [in progress]" in output


def test_list_filters_by_concept(tmp_path: Path) -> None:
    output = run(tmp_path, ["list", "--concept", "join"])

    assert output.count("\n") == 5
    assert "join-01" in output


def test_generate_reports_failure_with_mock_provider(tmp_path: Path) -> None:
    out = io.StringIO()
    code = main(
        ["--db", str(tmp_path / "p.db"), "--data-dir", str(DATA_DIR),
         "generate", "--concept", "SELECT", "--attempts", "1"],
        out=out,
    )

    assert code == 1
