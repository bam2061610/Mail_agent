from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class DeepSeekError(RuntimeError):
    pass


class DeepSeekTimeoutError(DeepSeekError):
    pass


class DeepSeekRateLimitError(DeepSeekError):
    pass


class DeepSeekResponseError(DeepSeekError):
    pass


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
        raise RuntimeError("openai package is required for DeepSeek integration") from exc

    api_key = getattr(config, "openai_api_key", None)
    if not api_key:
        raise ValueError("DeepSeek API key is not configured")

    client = OpenAI(
        api_key=api_key,
        base_url=getattr(config, "deepseek_base_url", "https://api.deepseek.com"),
        timeout=getattr(config, "ai_timeout_seconds", 60),
    )

    retries = max(1, int(getattr(config, "ai_max_retries", 3) or 3))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
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
            return DeepSeekCallResult(content=content, model=getattr(config, "deepseek_model", "deepseek-chat"))
        except (APITimeoutError, TimeoutError) as exc:  # type: ignore[arg-type]
            last_error = exc
            logger.warning("DeepSeek timeout on attempt %s/%s: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(min(2 * attempt, 5))
                continue
            raise DeepSeekTimeoutError(str(exc)) from exc
        except RateLimitError as exc:  # type: ignore[arg-type]
            last_error = exc
            logger.warning("DeepSeek rate limit on attempt %s/%s: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(min(2 * attempt, 5))
                continue
            raise DeepSeekRateLimitError(str(exc)) from exc
        except DeepSeekResponseError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("DeepSeek request failed on attempt %s/%s: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(min(2 * attempt, 5))
                continue
            raise DeepSeekError(str(exc)) from exc

    raise DeepSeekError(str(last_error) if last_error else "DeepSeek call failed")
