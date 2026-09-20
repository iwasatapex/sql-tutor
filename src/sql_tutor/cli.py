import argparse
import sys

from sql_tutor.catalog import load_exercises
from sql_tutor.sql.engine import SQLEngine
from sql_tutor.storage.progress import ProgressStore
from sql_tutor.tutor.session import LearningSession


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive SQL Tutor")
    parser.add_argument("--exercises", default="data/exercises/basic.json")
    parser.add_argument("--progress-db", default="sql_tutor_progress.sqlite3")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exercises = load_exercises(args.exercises)
    engine = SQLEngine()
    store = ProgressStore(args.progress_db)
    session = LearningSession(exercises, engine, store)
    state = session.start()

    def display(current) -> None:
        print(f"\n[{current.current_exercise.exercise_id}] {current.current_exercise.title}")
        print(current.current_exercise.description)
        print("Commands: :next, :mastery, :quit")

    display(state)
    try:
        while True:
            query = input("\nsql> ").strip()
            if query == ":quit":
                return 0
            if query == ":next":
                display(session.next())
                continue
            if query == ":mastery":
                current = session.state.current_exercise
                mastery = session.tutor.get_mastery(current.exercise_id)
                print(f"{mastery.level.value}: {mastery.accuracy:.0%}")
                continue
            if not query:
                continue
            feedback = session.submit(query)
            print(feedback.message)
            print(feedback.reason)
            if feedback.hint:
                print(f"Hint: {feedback.hint.message}")
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    finally:
        engine.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())
