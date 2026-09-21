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
    max_response_bytes: int = 1_000_000,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )

    def _read_body(response: Any) -> str:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(65536, max_response_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_response_bytes:
                raise LLMProviderError(
                    f"Response from {url} is too large: {total} bytes exceeds "
                    f"{max_response_bytes} byte limit"
                )
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = _read_body(response)
    except urllib.error.HTTPError as error:
        try:
            detail = _read_body(error)
        except LLMProviderError:
            detail = error.read(max_response_bytes).decode("utf-8", errors="replace")
        raise LLMProviderError(
            f"HTTP {error.code} from {url}: {detail[:300]}"
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
