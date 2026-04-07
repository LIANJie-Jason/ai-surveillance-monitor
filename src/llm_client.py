"""LLM client with OpenAI primary / Anthropic fallback."""

from __future__ import annotations

import logging

import anthropic
import openai

logger = logging.getLogger(__name__)

_RETRIABLE_OPENAI = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
    openai.RateLimitError,
    ValueError,
)


class LLMClient:
    def __init__(self, openai_key: str, anthropic_key: str):
        if not openai_key or not anthropic_key:
            raise ValueError("Both openai_key and anthropic_key must be non-empty strings")
        self._openai = openai.OpenAI(api_key=openai_key)
        self._anthropic = anthropic.Anthropic(api_key=anthropic_key)

    def complete(
        self,
        prompt: str,
        model_primary: str = "gpt-4.1-mini",
        model_fallback: str = "claude-haiku-4-5-20251001",
        system: str = "",
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> tuple[str, str]:
        """Returns (response_text, provider_used). Provider is 'openai' or 'anthropic'.

        Tries OpenAI first; falls back to Anthropic on retriable errors
        (connection, timeout, server, rate-limit).  Non-retriable OpenAI
        errors (auth, bad request) propagate immediately.
        """
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        oai_error: Exception | None = None
        try:
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = self._openai.chat.completions.create(
                model=model_primary,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
                timeout=timeout,
            )
            if not response.choices:
                raise ValueError("OpenAI returned empty choices list")
            choice = response.choices[0]
            if not hasattr(choice, "message") or choice.message is None:
                raise ValueError("OpenAI returned choice without message")
            text = choice.message.content
            if text is None:
                raise ValueError("OpenAI returned None content (possible tool-call or truncation)")
            return (text, "openai")
        except (IndexError, AttributeError) as exc:
            oai_error = exc
            logger.warning("OpenAI malformed response (%s), falling back to Anthropic", type(exc).__name__)
        except _RETRIABLE_OPENAI as exc:
            oai_error = exc
            logger.warning("OpenAI call failed (%s), falling back to Anthropic", type(exc).__name__)

        try:
            response = self._anthropic.messages.create(
                model=model_fallback,
                max_tokens=max_tokens,
                system=system or "You are a helpful assistant.",
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
            if not response.content:
                raise ValueError("Anthropic returned empty content")
            return (response.content[0].text, "anthropic")
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.BadRequestError,
        ) as ant_error:
            # Non-retriable: propagate immediately so operators get a clear signal
            raise RuntimeError(
                f"Both LLM providers failed. "
                f"OpenAI: {type(oai_error).__name__}  "
                f"Anthropic: {type(ant_error).__name__}"
            ) from ant_error
        except Exception as ant_error:
            raise RuntimeError(
                f"Both LLM providers failed. "
                f"OpenAI: {type(oai_error).__name__}  "
                f"Anthropic: {type(ant_error).__name__}"
            ) from ant_error
