"""Доменные ошибки слоя LLM."""
from __future__ import annotations


class LLMError(Exception):
    """Базовая ошибка вызова модели."""

    retryable = True
    code = "llm_error"


class LLMTimeoutError(LLMError):
    retryable = True
    code = "llm_timeout"


class LLMHTTPError(LLMError):
    code = "llm_http_error"

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        # Повторяем только временные ошибки сервера и rate limit.
        self.retryable = status_code >= 500 or status_code == 429


class LLMResponseError(LLMError):
    """Ответ модели не распарсился (невалидная структура/JSON)."""

    retryable = False
    code = "llm_bad_response"


class LLMConfigError(LLMError):
    retryable = False
    code = "llm_config_error"


class LLMUnavailableError(LLMError):
    """Все попытки исчерпаны — сервис должен отдать fallback."""

    retryable = False
    code = "llm_unavailable"
