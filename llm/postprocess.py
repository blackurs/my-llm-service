"""Пост-обработка ответа модели."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from llm.errors import LLMResponseError

logger = logging.getLogger("llm.postprocess")

_FENCE_RE = re.compile(
    r"^```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```$", re.DOTALL
)
_JSON_KEYS = ("summary", "answer", "text", "result", "content")


class PostProcessError(LLMResponseError):
    """После очистки ответ оказался пустым или непригодным."""

    code = "postprocess_error"


def _strip_code_fences(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def _normalize(text: str) -> str:
    return " ".join(text.split())


def postprocess(raw: Optional[str]) -> str:
    """Чистит ответ модели и безопасно разбирает JSON, если он там есть."""
    if raw is None:
        raise PostProcessError("model returned empty response")

    text = _strip_code_fences(str(raw))
    if not text:
        raise PostProcessError("model returned empty response")

    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Невалидный JSON — не падаем, логируем и берём очищенный текст.
            logger.warning(
                "invalid_json_response",
                extra={"preview": text[:120]},
            )
        else:
            if isinstance(data, dict):
                for key in _JSON_KEYS:
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        return _normalize(value)

    normalized = _normalize(text)
    if not normalized:
        raise PostProcessError("model returned empty response")
    return normalized
