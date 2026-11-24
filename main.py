"""Точка входа: FastAPI-приложение, CLI-режим и демонстрация сценариев."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from api.middleware import RequestContextMiddleware
from api.routes import router
from cache.ttl_cache import TTLCache
from config.loader import AppConfig, load_config
from config.logging_setup import setup_logging
from llm.client import LLMClient
from services.summarize import SummarizeService

logger = logging.getLogger("main")

INDEX_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LLM Summarization Service</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; }
    h1 { font-size: 22px; }
    textarea { width: 100%; height: 140px; padding: 10px; box-sizing: border-box; }
    button { margin-top: 10px; padding: 10px 18px; cursor: pointer; }
    pre { background: #f4f4f4; padding: 12px; overflow: auto; white-space: pre-wrap; }
    .hint { color: #666; font-size: 13px; }
  </style>
</head>
<body>
  <h1>Суммаризация текста через LLM</h1>
  <p class="hint">POST /chat · сообщение 1–1000 символов · ответ кешируется на 10 минут</p>
  <textarea id="text" placeholder="Вставьте текст для краткого резюме..."></textarea>
  <button id="send">Отправить</button>
  <h3>Ответ</h3>
  <pre id="out">—</pre>
  <script>
    const out = document.getElementById("out");
    document.getElementById("send").onclick = async () => {
      out.textContent = "Загрузка...";
      try {
        const res = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: document.getElementById("text").value })
        });
        out.textContent = "HTTP " + res.status + "\\n" + JSON.stringify(await res.json(), null, 2);
      } catch (err) {
        out.textContent = "Ошибка сети: " + err;
      }
    };
  </script>
</body>
</html>
"""


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    config = config or load_config()
    setup_logging(config.logging)

    cache = TTLCache(
        ttl_seconds=config.cache.ttl_seconds,
        max_entries=config.cache.max_entries,
    )
    llm_client = LLMClient(config.llm)
    service = SummarizeService(config, llm_client, cache)

    application = FastAPI(
        title="LLM Summarization Service",
        version="1.0.0",
        description="Минимальный pipeline: API -> валидация -> prompt -> LLM -> postprocess -> cache",
    )
    application.state.config = config
    application.state.cache = cache
    application.state.service = service

    application.add_middleware(RequestContextMiddleware)
    application.include_router(router)

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        errors = exc.errors()
        message = "Некорректный запрос."
        if errors:
            first = errors[0]
            location = [
                str(part)
                for part in first.get("loc", ())
                if part not in ("body", "query", "path")
            ]
            field = ".".join(location) or "body"
            detail = first.get("msg", "invalid value")
            message = (
                f"Поле '{field}': {detail}" if field != "body" else detail
            )
        logger.warning(
            "validation_error",
            extra={"request_id": request_id, "detail": message},
        )
        return JSONResponse(
            status_code=400,
            content={
                "request_id": request_id,
                "error": {"code": "validation_error", "message": message},
                "fallback": False,
            },
        )

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return INDEX_HTML

    return application


app = create_app()


def run_demo() -> int:
    """Прогоняет 5 сценариев через реальный HTTP-стек (TestClient)."""
    from fastapi.testclient import TestClient

    from llm.providers import MockProvider

    application = create_app()

    # Демонстрация печатает результат в stdout, а INFO-логи пишутся в файл,
    # чтобы вывод сценариев не смешивался с JSON-логом.
    for handler in logging.getLogger().handlers:
        if not isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.CRITICAL)

    client = TestClient(application)

    def show(title: str, response) -> None:
        print("\n=== " + title + " ===")
        print("HTTP", response.status_code)
        try:
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
        except ValueError:
            print(response.text)

    sample = (
        "Python — это высокоуровневый язык программирования. "
        "Он широко используется в анализе данных, машинном обучении и веб-разработке. "
        "Синтаксис Python считается простым для изучения. "
        "Большое сообщество поддерживает множество библиотек."
    )

    r1 = client.post("/chat", json={"message": sample})
    show("1. Корректный запрос", r1)

    r2 = client.post("/chat", json={"message": sample})
    show("2. Повторный идентичный запрос (ожидается cache hit)", r2)

    r3 = client.post("/chat", json={"message": "   "})
    show("3. Некорректный ввод: пустое сообщение", r3)

    r4 = client.post("/chat", json={"message": "x" * 1001})
    show("4. Некорректный ввод: слишком длинный текст", r4)

    config = application.state.config
    application.state.service.llm_client.provider = MockProvider(
        config.llm, fail_mode="always"
    )
    r5 = client.post("/chat", json={"message": "Проверка недоступности модели."})
    show("5. Эмуляция сбоя сети (ожидается fallback, HTTP 503)", r5)

    print("\n=== Статистика кеша ===")
    print(json.dumps(application.state.cache.stats(), ensure_ascii=False, indent=2))
    return 0


def run_cli(text: str) -> int:
    config = load_config()
    setup_logging(config.logging)
    cache = TTLCache(
        ttl_seconds=config.cache.ttl_seconds,
        max_entries=config.cache.max_entries,
    )
    service = SummarizeService(config, LLMClient(config.llm), cache)
    result = service.handle(text, request_id="cli")

    if result.fallback:
        print(result.answer)
        return 2
    if result.postprocess_error:
        print("Ошибка обработки ответа модели:", result.postprocess_error)
        return 3

    print(result.answer)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LLM summarization service (FastAPI)"
    )
    parser.add_argument(
        "--demo", action="store_true", help="прогнать демонстрационные сценарии"
    )
    parser.add_argument(
        "--cli", metavar="TEXT", help="обработать один текст из командной строки"
    )
    parser.add_argument("--host", help="хост для uvicorn")
    parser.add_argument("--port", type=int, help="порт для uvicorn")
    args = parser.parse_args()

    if args.demo:
        return run_demo()
    if args.cli:
        return run_cli(args.cli)

    config = load_config()
    uvicorn.run(
        app,
        host=args.host or config.server.host,
        port=args.port or config.server.port,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
