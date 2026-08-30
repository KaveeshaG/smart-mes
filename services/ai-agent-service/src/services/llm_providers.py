"""
LLM Providers — pluggable backends behind a single interface.

This is the seam for the cloud-vs-local comparative evaluation: `LLMService`
talks only to `BaseLLMProvider`, so swapping `LLM_PROVIDER=anthropic` for
`LLM_PROVIDER=ollama` changes nothing about prompt construction, JSON
parsing, or the rule-based fallback — only which model actually answers.
That makes provider a clean independent variable rather than a fork in the
agent logic.

Each provider returns raw text (or None on failure/timeout) and reports
whether it actually reached the model, so `LLMService` can distinguish
"model answered but gave bad JSON" from "model was unreachable" — both feed
the same `llm_used=False` fallback path today, but are logged separately for
the reliability metric (JSON-schema-validity rate) used in evaluation.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional

import anthropic
import httpx
from loguru import logger


class BaseLLMProvider(ABC):
    """Common interface every LLM backend implements."""

    #: Short id used in audit logs / experiment CSVs, e.g. "anthropic", "ollama".
    provider_id: str
    #: Model identifier reported alongside provider_id (e.g. "claude-haiku-4-5-20251001",
    #: "llama3.2:3b").
    model_id: str

    @abstractmethod
    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: int, tag: str
    ) -> Optional[str]:
        """
        Run one completion. Returns the raw text response, or None if the
        call failed or timed out — callers treat None as "use fallback".
        """
        raise NotImplementedError


class AnthropicProvider(BaseLLMProvider):
    """Cloud provider — Claude via the Anthropic API."""

    provider_id = "anthropic"

    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self.model_id = model
        self._timeout = timeout_seconds
        self._has_key = bool(api_key)
        self._client = anthropic.AsyncAnthropic(api_key=api_key or "dummy")

    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: int, tag: str
    ) -> Optional[str]:
        if not self._has_key:
            logger.debug(f"[{tag}][anthropic] No API key — using fallback")
            return None

        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self.model_id,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                ),
                timeout=self._timeout,
            )
            content = response.content[0].text.strip()
            logger.debug(
                f"[{tag}][anthropic] response ({len(content)} chars): {content[:120]}…"
            )
            return content

        except asyncio.TimeoutError:
            logger.warning(
                f"[{tag}][anthropic] call timed out after {self._timeout}s — using fallback"
            )
            return None
        except anthropic.APIError as exc:
            logger.warning(f"[{tag}][anthropic] API error: {exc} — using fallback")
            return None
        except Exception as exc:
            logger.error(f"[{tag}][anthropic] Unexpected error: {exc}")
            return None


class OllamaProvider(BaseLLMProvider):
    """
    Local provider — a model served by Ollama (http://localhost:11434 by
    default). Uses Ollama's `format: "json"` mode so the model is constrained
    to emit valid JSON, same intent as the Anthropic prompt's "respond ONLY
    with valid JSON" instruction, but grammar-enforced rather than requested.
    """

    provider_id = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self.model_id = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: int, tag: str
    ) -> Optional[str]:
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"num_predict": max_tokens},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                resp = await asyncio.wait_for(
                    http.post(f"{self._base_url}/api/chat", json=payload),
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"].strip()
                logger.debug(
                    f"[{tag}][ollama:{self.model_id}] response "
                    f"({len(content)} chars): {content[:120]}…"
                )
                return content

        except asyncio.TimeoutError:
            logger.warning(
                f"[{tag}][ollama:{self.model_id}] call timed out after "
                f"{self._timeout}s — using fallback"
            )
            return None
        except httpx.ConnectError:
            logger.warning(
                f"[{tag}][ollama:{self.model_id}] could not reach {self._base_url} "
                "— is `ollama serve` running? Using fallback"
            )
            return None
        except Exception as exc:
            logger.error(f"[{tag}][ollama:{self.model_id}] Unexpected error: {exc}")
            return None


def create_provider(settings) -> BaseLLMProvider:
    """Factory: build the active provider from settings.llm_provider."""
    if settings.llm_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    if settings.llm_provider != "anthropic":
        logger.warning(
            f"Unknown LLM_PROVIDER={settings.llm_provider!r} — defaulting to anthropic"
        )
    return AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
