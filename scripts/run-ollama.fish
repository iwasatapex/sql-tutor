#!/usr/bin/env fish
# Start SQL Tutor with a locally-created Ollama SQL model.
# Usage: ./scripts/run-ollama.fish [granite|gemma]

set choice (string lower -- (test (count $argv) -gt 0; and echo $argv[1]; or echo granite))

switch $choice
    case granite
        set -gx SQL_TUTOR_LLM_MODEL granite-sql:latest
    case gemma
        set -gx SQL_TUTOR_LLM_MODEL gemma-sql:latest
    case '*'
        echo 'Usage: ./scripts/run-ollama.fish [granite|gemma]'
        exit 2
end

set -gx SQL_TUTOR_LLM_PROVIDER ollama
set -gx SQL_TUTOR_LLM_BASE_URL http://127.0.0.1:11434
set -gx SQL_TUTOR_LLM_TIMEOUT 180

if not type -q ollama
    echo 'Error: ollama is not installed or not on PATH.'
    exit 1
end

if not ollama list | string match -q -- "$SQL_TUTOR_LLM_MODEL*"
    echo "Error: Ollama model '$SQL_TUTOR_LLM_MODEL' is not installed."
    echo 'Run: ollama list'
    exit 1
end

if not curl --silent --fail http://127.0.0.1:11434/api/tags >/dev/null
    echo 'Error: Ollama server is not reachable at http://127.0.0.1:11434.'
    echo 'Start it with: ollama serve'
    exit 1
end

python -m sql_tutor web
