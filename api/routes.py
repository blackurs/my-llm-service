"""Эндпоинты сервиса."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.schemas import ChatRequest, ChatResponse, ErrorResponse
from services.summarize import FALLBACK_ANSWER

logger = logging.getLogger("api.routes")

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    service = request.app.state.service
    return {
        "status": "ok",
        "provider": service.llm_client.provider.name,
        "model": service.config.llm.model,
        "cache": service.cache.stats(),
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Ошибка валидации"},
        502: {"model": ErrorResponse, "description": "Некорректный ответ модели"},
        503: {"model": ErrorResponse, "description": "Модель недоступна (fallback)"},
    },
)
def chat(payload: ChatRequest, request: Request):
    service = request.app.state.service
    request_id = getattr(request.state, "request_id", "-")

    result = service.handle(
        payload.message,
        request_id=request_id,
        scenario=payload.scenario,
        temperature=payload.temperature,
        model=payload.model,
    )

    if result.fallback:
        return JSONResponse(
            status_code=503,
            content={
                "request_id": request_id,
                "answer": FALLBACK_ANSWER,
                "cached": False,
                "fallback": True,
                "error": {
                    "code": "llm_unavailable",
                    "message": FALLBACK_ANSWER,
                },
            },
        )

    if result.postprocess_error:
        return JSONResponse(
            status_code=502,
            content={
                "request_id": request_id,
                "answer": "",
                "cached": False,
                "fallback": False,
                "error": {
                    "code": "bad_model_response",
                    "message": (
                        "Модель вернула некорректный ответ. Попробуйте ещё раз."
                    ),
                },
            },
        )

    return ChatResponse(
        request_id=request_id,
        answer=result.answer,
        cached=result.cached,
        fallback=False,
        model=result.model,
        attempts=result.attempts,
        elapsed_ms=round(result.elapsed_ms, 2),
    )
