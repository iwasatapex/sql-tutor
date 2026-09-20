# Architecture

```
cli.py                      argparse front end, interactive practice loop
config.py                   Settings.from_env
sql/                        engine (sandboxed SQLite), safety, comparator, evaluator
exercises/                  models, validator, verifier, repository (JSON), generator
learning/                   curriculum, mastery, difficulty, selector (adaptive choice)
tutor/                      hints, orchestrator (evaluate + feedback), session (workflow)
storage/progress.py         SQLite attempt log
llm/                        base, mock, ollama, openai_compatible, factory, http
data/                       datasets/, exercises/, curriculum/ (reserved)
```

Flow of one practice turn:

1. `LearningSession.next_exercise` asks `ExerciseSelector` for an exercise
   given the full attempt history, and builds a fresh in-memory database from
   the exercise's `setup_sql`.
2. `LearningSession.submit` calls `TutorOrchestrator.submit_query`, which
   evaluates the query against the expected result, records the attempt, and
   returns feedback (plus a hint if one was requested).
3. Repeated failures attach an escalating hint; a correct answer ends the
   exercise and the loop selects the next one.
