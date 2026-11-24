"""Вызов LLM с таймаутом, ретраями и экспоненциальной задержкой."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from config.loader import LLMConfig
from llm.errors import LLMError, LLMUnavailableError
from llm.providers import BaseProvider, Message, create_provider

logger = logging.getLogger("llm.client")


@dataclass
class GenerationResult:
    text: str
    attempts: int
    elapsed_ms: float


class LLMClient:
    def __init__(
        self,
        config: LLMConfig,
        provider: Optional[BaseProvider] = None,
        sleep_func: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.config = config
        self.provider = provider or create_provider(config)
        self._sleep = sleep_func or time.sleep

    def generate(
        self,
        messages: List[Message],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> GenerationResult:
        model = model or self.config.model
        temperature = (
            self.config.temperature if temperature is None else temperature
        )
        max_attempts = max(1, int(self.config.max_retries))
        started = time.perf_counter()
        last_error: Optional[LLMError] = None

        for attempt in range(1, max_attempts + 1):
            attempt_started = time.perf_counter()
            try:
                text = self.provider.generate(
                    messages,
                    model=model,
                    temperature=temperature,
                    timeout=self.config.timeout_seconds,
                )
                elapsed_ms = (time.perf_counter() - attempt_started) * 1000
                logger.info(
                    "llm_call_ok",
                    extra={
                        "provider": self.provider.name,
                        "model": model,
                        "attempt": attempt,
                        "elapsed_ms": round(elapsed_ms, 2),
                    },
                )
                return GenerationResult(
                    text=text,
                    attempts=attempt,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )
            except LLMError as exc:
                last_error = exc
                elapsed_ms = (time.perf_counter() - attempt_started) * 1000
                logger.warning(
                    "llm_call_failed",
                    extra={
                        "provider": self.provider.name,
                        "model": model,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                        "error": str(exc),
                        "elapsed_ms": round(elapsed_ms, 2),
                    },
                )

                if not exc.retryable or attempt >= max_attempts:
                    break

                delay = min(
                    self.config.backoff_base_seconds * (2 ** (attempt - 1)),
                    self.config.backoff_max_seconds,
                )
                delay += random.uniform(0, 0.1)
                logger.info(
                    "llm_retry_scheduled",
                    extra={"attempt": attempt + 1, "delay_seconds": round(delay, 3)},
                )
                self._sleep(delay)

        logger.error(
            "llm_unavailable",
            extra={
                "provider": self.provider.name,
                "attempts": max_attempts,
                "last_error": str(last_error) if last_error else "unknown",
            },
        )
        raise LLMUnavailableError(
            f"LLM is unavailable after {max_attempts} attempt(s): {last_error}"
        ) from last_error
