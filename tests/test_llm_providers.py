import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sql_tutor.config import Settings
from sql_tutor.llm.base import LLMProviderError
from sql_tutor.llm.factory import create_provider
from sql_tutor.llm.http import post_json
from sql_tutor.llm.mock import MockLLMProvider
from sql_tutor.llm.models import LLMRequest
from sql_tutor.llm.ollama import OllamaProvider
from sql_tutor.llm.openai_compatible import OpenAICompatibleProvider


class FakeServer:
    def __init__(self, status: int, body: str) -> None:
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                outer.requests.append({
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(self.rfile.read(length)),
                })
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *args: object) -> None:
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def make_server():
    servers: list[FakeServer] = []

    def factory(status: int, body: str) -> FakeServer:
        server = FakeServer(status, body)
        servers.append(server)
        return server

    yield factory

    for server in servers:
        server.close()


def test_ollama_sends_chat_request_and_parses_reply(make_server) -> None:
    server = make_server(200, json.dumps({
        "model": "m", "message": {"role": "assistant", "content": "hi"},
        "prompt_eval_count": 5, "eval_count": 7,
    }))

    response = OllamaProvider("m", base_url=server.url).generate(
        LLMRequest(prompt="q", system_prompt="s", json_mode=True)
    )

    sent = server.requests[0]
    assert sent["path"] == "/api/chat"
    assert sent["body"]["model"] == "m"
    assert sent["body"]["stream"] is False
    assert sent["body"]["format"] == "json"
    assert [m["role"] for m in sent["body"]["messages"]] == ["system", "user"]
    assert response.content == "hi"
    assert response.usage == {"prompt_tokens": 5, "completion_tokens": 7}


def test_ollama_omits_json_format_by_default(make_server) -> None:
    server = make_server(200, json.dumps({"message": {"content": "x"}}))

    OllamaProvider("m", base_url=server.url).generate(LLMRequest(prompt="q"))

    assert "format" not in server.requests[0]["body"]


def test_ollama_http_error_becomes_provider_error(make_server) -> None:
    server = make_server(404, '{"error": "model not found"}')

    with pytest.raises(LLMProviderError, match="404"):
        OllamaProvider("m", base_url=server.url).generate(
            LLMRequest(prompt="q")
        )


def test_ollama_unexpected_shape_becomes_provider_error(make_server) -> None:
    server = make_server(200, '{"unexpected": true}')

    with pytest.raises(LLMProviderError, match="Unexpected"):
        OllamaProvider("m", base_url=server.url).generate(
            LLMRequest(prompt="q")
        )


def test_unreachable_server_becomes_provider_error() -> None:
    provider = OllamaProvider(
        "m", base_url="http://127.0.0.1:9", timeout_seconds=1
    )

    with pytest.raises(LLMProviderError, match="Could not reach"):
        provider.generate(LLMRequest(prompt="q"))


def test_http_client_rejects_oversized_responses(make_server) -> None:
    server = make_server(200, "x" * 1024)

    with pytest.raises(LLMProviderError, match="too large|size"):
        post_json(server.url, {"hello": "world"}, max_response_bytes=64)


def test_openai_compatible_request_and_auth(make_server) -> None:
    server = make_server(200, json.dumps({
        "model": "m",
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"total_tokens": 3},
    }))

    response = OpenAICompatibleProvider(
        "m", base_url=server.url + "/v1", api_key="secret"
    ).generate(LLMRequest(prompt="q", json_mode=True))

    sent = server.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["auth"] == "Bearer secret"
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert response.content == "hello"
    assert response.usage == {"total_tokens": 3}


def test_factory_builds_each_provider(tmp_path) -> None:
    base = dict(data_dir=tmp_path, database_path=tmp_path / "db")

    assert isinstance(create_provider(Settings(**base)), MockLLMProvider)
    assert isinstance(
        create_provider(Settings(**base, llm_provider="ollama", llm_model="m")),
        OllamaProvider,
    )
    assert isinstance(
        create_provider(Settings(
            **base, llm_provider="openai-compatible", llm_model="m",
            llm_base_url="http://x/v1",
        )),
        OpenAICompatibleProvider,
    )


@pytest.mark.parametrize("overrides", [
    {"llm_provider": "ollama"},
    {"llm_provider": "openai-compatible", "llm_model": "m"},
    {"llm_provider": "nonsense", "llm_model": "m"},
])
def test_factory_rejects_bad_configuration(tmp_path, overrides) -> None:
    settings = Settings(
        data_dir=tmp_path, database_path=tmp_path / "db", **overrides
    )

    with pytest.raises(LLMProviderError):
        create_provider(settings)


def test_settings_from_env(tmp_path) -> None:
    settings = Settings.from_env({
        "SQL_TUTOR_DATA_DIR": str(tmp_path),
        "SQL_TUTOR_DB": str(tmp_path / "x.db"),
        "SQL_TUTOR_LLM_PROVIDER": "Ollama",
        "SQL_TUTOR_LLM_MODEL": "m",
        "SQL_TUTOR_LLM_TIMEOUT": "30",
    })

    assert settings.llm_provider == "ollama"
    assert settings.llm_model == "m"
    assert settings.llm_timeout_seconds == 30.0
    assert settings.database_path == tmp_path / "x.db"
