import json
import urllib.error
import urllib.request
from typing import Any

from sql_tutor.llm.base import LLMProviderError


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise LLMProviderError(
            f"HTTP {error.code} from {url}: {detail}"
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise LLMProviderError(
            f"Could not reach {url}: {error}"
        ) from error

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise LLMProviderError(
            f"Non-JSON response from {url}: {body[:200]}"
        ) from error

    if not isinstance(parsed, dict):
        raise LLMProviderError(f"Unexpected response shape from {url}")

    return parsed
