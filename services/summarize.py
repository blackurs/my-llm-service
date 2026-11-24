"""Бизнес-логика: суммаризация через LLM с кешем и fallback."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from cache.ttl_cache import TTLCache
from config.loader import AppConfig
from llm.client import LLMClient
from llm.errors import LLMUnavailableError
from llm.postprocess import PostProcessError, postprocess
from llm.prompts import build_prompt

logger = logging.getLogger("services.summarize")

FALLBACK_ANSWER = "Сервис временно недоступен, попробуйте позже."


@dataclass
class ServiceResult:
    answer: str
    cached: bool
    fallback: bool
    model: str
    attempts: int
    elapsed_ms: float
    cache_key: str
    scenario: str
    postprocess_error: Optional[str] = None


class SummarizeService:
    def __init__(
        self,
        config: AppConfig,
        llm_client: LLMClient,
        cache: TTLCache,
    ) -> None:
        self.config = config
        self.llm_client = llm_client
        self.cache = cache

    def handle(
        self,
        message: str,
        *,
        request_id: str = "-",
        scenario: str = "summarize",
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> ServiceResult:
        started = time.perf_counter()

        model = model or self.config.llm.model
        temperature = (
            self.config.llm.temperature if temperature is None else temperature
        )

        bundle = build_prompt(message, scenario)
        logger.info(
            "prompt_built",
            extra={
                "request_id": request_id,
                "scenario": scenario,
                "model": model,
                "temperature": temperature,
                "system_prompt": bundle.system_prompt,
                "prompt_chars": len(bundle.messages[-1]["content"]),
            },
        )

        cache_key = self.cache.make_key(
            text=message,
            model=model,
            temperature=temperature,
            system_prompt=bundle.system_prompt,
            scenario=scenario,
        )

        cached_answer = self.cache.get(cache_key)
        if cached_answer is not None:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "cached": True,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
            return ServiceResult(
                answer=cached_answer,
                cached=True,
                fallback=False,
                model=model,
                attempts=0,
                elapsed_ms=elapsed_ms,
                cache_key=cache_key,
                scenario=scenario,
            )

        try:
            generation = self.llm_client.generate(
                bundle.messages, model=model, temperature=temperature
            )
        except LLMUnavailableError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "fallback_returned",
                extra={
                    "request_id": request_id,
                    "error": str(exc),
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
            return ServiceResult(
                answer=FALLBACK_ANSWER,
                cached=False,
                fallback=True,
                model=model,
                attempts=self.config.llm.max_retries,
                elapsed_ms=elapsed_ms,
                cache_key=cache_key,
                scenario=scenario,
            )

        try:
            answer = postprocess(generation.text)
        except PostProcessError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "postprocess_failed",
                extra={
                    "request_id": request_id,
                    "error": str(exc),
                    "raw_preview": generation.text[:120],
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
            return ServiceResult(
                answer="",
                cached=False,
                fallback=False,
                model=model,
                attempts=generation.attempts,
                elapsed_ms=elapsed_ms,
                cache_key=cache_key,
                scenario=scenario,
                postprocess_error=str(exc),
            )

        self.cache.set(cache_key, answer)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "cached": False,
                "attempts": generation.attempts,
                "answer_chars": len(answer),
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        return ServiceResult(
            answer=answer,
            cached=False,
            fallback=False,
            model=model,
            attempts=generation.attempts,
            elapsed_ms=elapsed_ms,
            cache_key=cache_key,
            scenario=scenario,
        )
