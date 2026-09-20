# SQL Tutor

A local-first, model-agnostic SQL learning tutor.

## Features

- Read-only SQLite execution and SQL safety checks
- Exercise validation and LLM-generated exercise support
- Curriculum, difficulty adjustment, and mastery tracking
- Persistent attempt history
- Adaptive exercise selection
- Stateful learning sessions
- Interactive CLI
- OpenAI-compatible HTTP provider without third-party runtime dependencies

## Setup

```bash
conda activate projects
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Run the CLI

```bash
python -m sql_tutor.cli --exercises data/exercises/basic.json
```

The bundled catalog is metadata only. Supply your own setup statements or extend the session bootstrap before using exercises against a populated schema.

## Provider example

```python
from sql_tutor.llm.http import OpenAICompatibleProvider

provider = OpenAICompatibleProvider(
    base_url="http://localhost:1234/v1",
    model="your-model",
)
```
