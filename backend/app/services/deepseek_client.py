from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.exceptions import AiError

logger = logging.getLogger(__name__)


class DeepSeekError(AiError):
    """Base DeepSeek client error."""


class DeepSeekTimeoutError(DeepSeekError):
    """Raised when DeepSeek times out."""


class DeepSeekRateLimitError(DeepSeekError):
    """Raised when DeepSeek rate limits a request."""


class DeepSeekResponseError(DeepSeekError):
    """Raised when DeepSeek returns an invalid payload."""


@dataclass(slots=True)
class DeepSeekCallResult:
    content: str
    model: str


def call_deepseek_chat(
    *,
    system_prompt: str,
    user_payload: str,
    config,
    response_format: dict[str, Any] | None = None,
) -> DeepSeekCallResult:
    try:
        from openai import OpenAI
        try:
            from openai import APITimeoutError, RateLimitError
        except ImportError:  # pragma: no cover
            APITimeoutError = TimeoutError  # type: ignore[assignment]
            RateLimitError = RuntimeError  # type: ignore[assignment]
    except ImportError as exc:  # pragma: no cover
        raise DeepSeekError("openai package is required for DeepSeek integration") from exc

    api_key = getattr(config, "deepseek_api_key", None) or getattr(config, "openai_api_key", None)
    if not api_key:
        raise ValueError("DeepSeek API key is not configured")

    client = OpenAI(
        api_key=api_key,
        base_url=getattr(config, "deepseek_base_url", "https://api.deepseek.com"),
        timeout=getattr(config, "ai_timeout_seconds", 60),
    )
    retries = max(1, int(getattr(config, "ai_max_retries", 3) or 3))

    @retry(
        retry=retry_if_exception_type(DeepSeekError),
        stop=stop_after_attempt(retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _request() -> DeepSeekCallResult:
        try:
            response = client.chat.completions.create(
                model=getattr(config, "deepseek_model", "deepseek-chat"),
                response_format=response_format or {"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_payload},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise DeepSeekResponseError("Empty DeepSeek response")
            return DeepSeekCallResult(
                content=content,
                model=getattr(config, "deepseek_model", "deepseek-chat"),
            )
        except (APITimeoutError, TimeoutError) as exc:  # type: ignore[arg-type]
            logger.warning("DeepSeek timeout", exc_info=True)
            raise DeepSeekTimeoutError(str(exc)) from exc
        except RateLimitError as exc:  # type: ignore[arg-type]
            logger.warning("DeepSeek rate limit", exc_info=True)
            raise DeepSeekRateLimitError(str(exc)) from exc
        except DeepSeekResponseError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek request failed", exc_info=True)
            raise DeepSeekError(str(exc)) from exc

    return _request()
