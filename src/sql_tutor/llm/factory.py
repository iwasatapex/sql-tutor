from sql_tutor.config import Settings
from sql_tutor.llm.base import LLMProvider, LLMProviderError
from sql_tutor.llm.mock import MockLLMProvider
from sql_tutor.llm.ollama import OllamaProvider
from sql_tutor.llm.openai_compatible import OpenAICompatibleProvider


def create_provider(settings: Settings) -> LLMProvider:
    name = settings.llm_provider

    if name == "mock":
        return MockLLMProvider()

    if not settings.llm_model:
        raise LLMProviderError(
            "SQL_TUTOR_LLM_MODEL must be set for the "
            f"'{name}' provider"
        )

    if name == "ollama":
        return OllamaProvider(
            settings.llm_model,
            base_url=settings.llm_base_url or "http://localhost:11434",
            timeout_seconds=settings.llm_timeout_seconds,
        )

    if name in ("openai", "openai-compatible"):
        if not settings.llm_base_url:
            raise LLMProviderError(
                "SQL_TUTOR_LLM_BASE_URL must be set for the "
                f"'{name}' provider (e.g. http://localhost:8080/v1)"
            )

        return OpenAICompatibleProvider(
            settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    raise LLMProviderError(
        f"Unknown LLM provider '{name}'. "
        "Use mock, ollama, or openai-compatible."
    )
