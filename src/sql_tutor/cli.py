import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from sql_tutor.config import OLLAMA_MODELS, Settings
from sql_tutor.exercises.generator import (
    ExerciseGenerationError,
    ExerciseGenerator,
)
from sql_tutor.exercises.models import Exercise, ExerciseDifficulty
from sql_tutor.exercises.repository import (
    ExerciseLoadError,
    ExerciseRepository,
    exercise_to_payload,
)
from sql_tutor.learning.curriculum import Curriculum
from sql_tutor.learning.selector import ExerciseSelector
from sql_tutor.llm.base import LLMProviderError
from sql_tutor.llm.factory import create_provider
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.orchestrator import TutorOrchestrator
from sql_tutor.tutor.session import ExerciseSetupError, LearningSession

InputFn = Callable[[str], str]

HELP_TEXT = (
    "Type your SQL and finish with ';' (or a blank line).\n"
    "Commands:  :hint  :schema  :skip  :help  :quit"
)


def choose_ollama_model(input_fn: InputFn = input) -> str:
    print("\nChoose an Ollama model:")

    for index, (label, model) in enumerate(OLLAMA_MODELS, start=1):
        print(f"  {index}. {label} ({model})")

    while True:
        try:
            choice = input_fn("Model [1-3]: ").strip()
        except EOFError as error:
            raise LLMProviderError(
                "Model selection cancelled."
            ) from error

        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(OLLAMA_MODELS):
                label, model = OLLAMA_MODELS[index]
                print(f"Using {label}: {model}")
                return model

        print("Invalid selection. Choose 1, 2, or 3.")


def format_table(
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    max_rows: int = 10,
) -> str:
    shown = [
        ["NULL" if v is None else str(v) for v in row]
        for row in rows[:max_rows]
    ]
    widths = [
        max([len(str(c))] + [len(r[i]) for r in shown])
        for i, c in enumerate(columns)
    ]

    def line(cells: Sequence[str]) -> str:
        return " | ".join(c.ljust(w) for c, w in zip(cells, widths))

    out = [line([str(c) for c in columns]), "-+-".join("-" * w for w in widths)]
    out.extend(line(r) for r in shown)

    if len(rows) > max_rows:
        out.append(f"... {len(rows) - max_rows} more rows")

    return "\n".join(out)


def format_schema(exercise: Exercise) -> str:
    lines = []

    for table in exercise.schema:
        columns = ", ".join(
            f"{c.name} {c.data_type}" for c in table.columns
        )
        lines.append(f"  {table.name}({columns})")

    return "\n".join(lines)


def read_query(input_fn: InputFn) -> str | None:
    """Read a query or a ':' command. Returns None on EOF."""
    lines: list[str] = []
    prompt = "sql> "

    while True:
        try:
            line = input_fn(prompt)
        except EOFError:
            return None

        stripped = line.strip()

        if not lines and stripped.startswith(":"):
            return stripped.lower()

        if not stripped:
            if lines:
                return "\n".join(lines)
            continue

        lines.append(line)

        if stripped.endswith(";"):
            return "\n".join(lines)

        prompt = "...> "


def run_practice(
    session: LearningSession,
    input_fn: InputFn = input,
    out: TextIO = sys.stdout,
) -> None:
    def say(text: str = "") -> None:
        print(text, file=out)

    say("SQL Tutor. " + HELP_TEXT)

    while True:
        exercise = session.next_exercise()

        if exercise is None:
            say("\nNo more exercises available. Nice work!")
            return

        say(f"\n[{exercise.concept} / {exercise.difficulty.value}] "
            f"{exercise.title}")
        say(exercise.description)
        say("Tables:")
        say(format_schema(exercise))

        while True:
            entry = read_query(input_fn)

            if entry is None or entry == ":quit":
                say("\nGoodbye.")
                return

            if entry == ":help":
                say(HELP_TEXT)
                continue

            if entry == ":schema":
                say(format_schema(exercise))
                continue

            if entry == ":hint":
                say(f"Hint: {session.request_hint().message}")
                continue

            if entry == ":skip":
                session.skip()
                say("Skipped.")
                break

            if entry.startswith(":"):
                say(f"Unknown command {entry}. Try :help")
                continue

            outcome = session.submit(entry)
            feedback = outcome.feedback
            say(feedback.message)

            if feedback.is_correct:
                break

            if feedback.error:
                say(f"Error: {feedback.error}")
            else:
                say(feedback.reason)
                result = session.preview(entry)

                if result is not None:
                    say("Your query returned:")
                    say(format_table(result.columns, result.rows))

            if feedback.hint is not None:
                say(f"Hint: {feedback.hint.message}")


def show_progress(session: LearningSession, out: TextIO) -> None:
    for progress in session.topic_progress():
        if progress.is_complete:
            status = "done"
        elif progress.attempts:
            status = "in progress"
        else:
            status = "not started"

        recent = (
            f"{progress.mastery.level.value}, "
            f"{progress.mastery.accuracy:.0%} recent accuracy"
            if progress.attempts else "-"
        )
        print(
            f"{progress.topic.order}. {progress.topic.title:<9} "
            f"{progress.solved}/{progress.total_exercises} solved  "
            f"[{status}]  {recent}",
            file=out,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sql-tutor",
        description="A local-first adaptive SQL tutor.",
    )
    parser.add_argument("--db", type=Path, help="progress database path")
    parser.add_argument("--data-dir", type=Path, help="exercise data directory")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("practice", help="start an adaptive practice session")
    sub.add_parser("progress", help="show progress per topic")
    web_cmd = sub.add_parser("web", help="start the browser UI")
    web_cmd.add_argument("--host", default="127.0.0.1")
    web_cmd.add_argument("--port", type=int, default=8765)
    web_cmd.add_argument("--open", action="store_true", dest="open_browser")

    list_cmd = sub.add_parser("list", help="list available exercises")
    list_cmd.add_argument("--concept")

    gen = sub.add_parser("generate", help="generate an exercise with an LLM")
    gen.add_argument("--concept", required=True)
    gen.add_argument(
        "--difficulty",
        choices=[d.value for d in ExerciseDifficulty],
        default=ExerciseDifficulty.BEGINNER.value,
    )
    gen.add_argument("--attempts", type=int, default=3)
    gen.add_argument(
        "--save",
        action="store_true",
        help="save into data/exercises/generated/",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: InputFn = input,
    out: TextIO = sys.stdout,
) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    settings = Settings.from_env()

    if settings.llm_provider == "ollama" and not settings.llm_model:
        selected_model = settings.llm_model or choose_ollama_model(input_fn)
        settings = Settings(
            **{
                **settings.__dict__,
                "llm_model": selected_model,
            }
        )

    if args.db:
        settings = Settings(**{**settings.__dict__, "database_path": args.db})

    if args.data_dir:
        settings = Settings(**{**settings.__dict__, "data_dir": args.data_dir})

    try:
        repository = ExerciseRepository.from_directory(settings.data_dir)
    except ExerciseLoadError as error:
        print(f"Could not load exercises: {error}", file=sys.stderr)
        return 2

    command = args.command or "practice"

    if command == "web":
        from sql_tutor.web import serve

        try:
            serve(settings, host=args.host, port=args.port, open_browser=args.open_browser)
        except (LLMProviderError, ExerciseLoadError, OSError) as error:
            print(f"Web UI failed: {error}", file=sys.stderr)
            return 1
        return 0

    if command == "list":
        exercises = (
            repository.for_concept(args.concept)
            if args.concept else repository.all()
        )
        for e in exercises:
            print(f"{e.exercise_id:<14} {e.concept:<9} "
                  f"{e.difficulty.value:<13} {e.title}", file=out)
        return 0

    if command == "generate":
        try:
            generator = ExerciseGenerator(
                create_provider(settings),
                max_attempts=args.attempts,
                verify=True,
            )
            exercise = generator.generate(
                args.concept, ExerciseDifficulty(args.difficulty)
            )
        except (LLMProviderError, ExerciseGenerationError) as error:
            print(f"Generation failed: {error}", file=sys.stderr)
            return 1

        print(json.dumps(exercise_to_payload(exercise), indent=2), file=out)

        if args.save:
            target = (
                settings.data_dir / "exercises" / "generated"
                / f"{exercise.exercise_id}.json"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps([exercise_to_payload(exercise)], indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Saved to {target}", file=sys.stderr)
        return 0

    store = ProgressStore(str(settings.database_path))
    llm_provider = None
    if settings.llm_provider != "mock":
        try:
            llm_provider = create_provider(settings)
        except LLMProviderError as error:
            print(f"LLM setup failed: {error}", file=sys.stderr)
            store.close()
            return 1

    session = LearningSession(
        repository=repository,
        selector=ExerciseSelector(Curriculum.default(), repository),
        progress_store=store,
        orchestrator=TutorOrchestrator(
            progress_store=store,
            llm_provider=llm_provider,
        ),
    )

    try:
        if command == "progress":
            show_progress(session, out)
        else:
            run_practice(session, input_fn, out)
    except KeyboardInterrupt:
        print("\nGoodbye.", file=out)
    except ExerciseSetupError as error:
        print(f"Exercise data problem: {error}", file=sys.stderr)
        return 1
    finally:
        session.close()
        store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
