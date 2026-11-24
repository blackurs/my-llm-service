"""Провайдеры LLM: mock (офлайн), OpenAI-совместимый, Anthropic."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

import httpx

from config.loader import LLMConfig
from llm.errors import (
    LLMConfigError,
    LLMError,
    LLMHTTPError,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger("llm.providers")

Message = Dict[str, str]


def _last_user_text(messages: List[Message]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _extract_payload(text: str) -> str:
    """Достаёт текст между маркерами <<< и >>>, если они есть."""
    match = re.search(r"<<<\s*(.*?)\s*>>>", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


class BaseProvider:
    name = "base"

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def generate(
        self,
        messages: List[Message],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        raise NotImplementedError


class MockProvider(BaseProvider):
    """Детерминированный офлайн-провайдер для демо и тестов.

    Умеет имитировать сбои: fail_mode="always" или "first_n".
    """

    name = "mock"

    def __init__(
        self,
        config: LLMConfig,
        fail_mode: str = "none",
        fail_times: int = 0,
    ) -> None:
        super().__init__(config)
        if fail_mode not in ("none", "always", "first_n"):
            raise ValueError(f"Unknown fail_mode: {fail_mode}")
        self.fail_mode = fail_mode
        self._failures_left = max(0, int(fail_times))
        self.calls = 0

    def generate(
        self,
        messages: List[Message],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        self.calls += 1

        if self.fail_mode == "always" or (
            self.fail_mode == "first_n" and self._failures_left > 0
        ):
            if self.fail_mode == "first_n":
                self._failures_left -= 1
            logger.info("mock_llm_failure", extra={"call": self.calls})
            raise LLMTimeoutError("simulated LLM timeout")

        payload = _extract_payload(_last_user_text(messages))
        return self._summarize(payload)

    @staticmethod
    def _summarize(text: str) -> str:
        clean = " ".join(text.split())
        if not clean:
            return "[mock-summary] (пустой текст)"
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        summary = " ".join(sentences[:2]).strip()
        if len(summary) > 220:
            summary = summary[:220].rstrip() + "…"
        elif len(clean) > len(summary):
            summary = summary.rstrip(".") + "…"
        return f"[mock-summary] {summary}"


class OpenAIProvider(BaseProvider):
    """Провайдер, совместимый с OpenAI Chat Completions API."""

    name = "openai"

    def generate(
        self,
        messages: List[Message],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        if not self.config.api_key:
            raise LLMConfigError("LLM_API_KEY is not set for provider 'openai'")

        base_url = self.config.base_url or "https://api.openai.com/v1"
        url = base_url.rstrip("/") + "/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        response = self._post(url, payload, headers, timeout)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError("provider returned non-JSON body") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                "unexpected OpenAI response structure"
            ) from exc

        if not isinstance(content, str):
            raise LLMResponseError("OpenAI content is not a string")
        return content

    @staticmethod
    def _post(
        url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float
    ) -> httpx.Response:
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"timeout after {timeout}s") from exc
        except httpx.RequestError as exc:
            raise LLMError(f"network error: {exc}") from exc

        if response.status_code >= 400:
            raise LLMHTTPError(
                response.status_code,
                f"provider returned {response.status_code}: "
                f"{response.text[:200]}",
            )
        return response


class AnthropicProvider(BaseProvider):
    """Провайдер Anthropic Messages API."""

    name = "anthropic"

    def generate(
        self,
        messages: List[Message],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        if not self.config.api_key:
            raise LLMConfigError("LLM_API_KEY is not set for provider 'anthropic'")

        base_url = self.config.base_url or "https://api.anthropic.com/v1"
        url = base_url.rstrip("/") + "/messages"

        system_parts = [
            m.get("content", "") for m in messages if m.get("role") == "system"
        ]
        user_messages = [m for m in messages if m.get("role") != "system"]

        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "system": "\n".join(part for part in system_parts if part),
            "messages": user_messages,
        }
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        response = OpenAIProvider._post(url, payload, headers, timeout)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError("provider returned non-JSON body") from exc

        try:
            text = data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                "unexpected Anthropic response structure"
            ) from exc

        if not isinstance(text, str):
            raise LLMResponseError("Anthropic content is not a string")
        return text


def create_provider(config: LLMConfig) -> BaseProvider:
    provider = (config.provider or "mock").strip().lower()
    if provider == "mock":
        return MockProvider(config)
    if provider == "openai":
        return OpenAIProvider(config)
    if provider == "anthropic":
        return AnthropicProvider(config)
    raise LLMConfigError(f"unknown LLM provider: {provider}")
