"""Pydantic-схемы API: валидация запроса и формат ответа."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_LENGTH = 1000


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=MAX_MESSAGE_LENGTH,
        description="Текст для суммаризации (1–1000 символов)",
        examples=["Python — язык программирования. Он популярен в анализе данных."],
    )
    scenario: Literal["summarize"] = Field(
        default="summarize", description="Сценарий обработки"
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Переопределить температуру модели (0–2)",
    )
    model: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Переопределить модель",
    )

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message не должно быть пустым")
        return stripped


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    cached: bool
    fallback: bool
    model: str
    attempts: int
    elapsed_ms: float


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail
    fallback: bool = False
