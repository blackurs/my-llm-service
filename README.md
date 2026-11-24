# LLM Summarization Service

Минимальный, но завершённый сервис: принимает текст, делает краткое резюме через
LLM и возвращает результат. Реализован как последовательный pipeline
**API → валидация → бизнес-логика → prompt builder → LLM → пост-обработка → кеш → ответ**.

Проект сделан по требованиям задания: таймауты, ретраи с экспоненциальной
задержкой, fallback, TTL-кеш с учётом параметров, структурированные JSON-логи,
тесты и документация.

---

## Содержание

- [Возможности](#возможности)
- [Архитектура](#архитектура)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [Провайдеры LLM](#провайдеры-llm)
- [API](#api)
- [Примеры запросов](#примеры-запросов)
- [Кеширование](#кеширование)
- [Устойчивость и ошибки](#устойчивость-и-ошибки)
- [Логирование](#логирование)
- [Тесты](#тесты)
- [Демонстрация](#демонстрация)
- [Структура проекта](#структура-проекта)
- [Ограничения](#ограничения)

---

## Возможности

| Требование | Реализация |
|---|---|
| UI | HTTP-эндпоинт FastAPI + простая веб-страница `GET /` + CLI (`--cli`, `--demo`) |
| API-слой | Pydantic-валидация: `message` 1–1000 символов, запрет пустого/пробельного |
| Бизнес-логика | Сценарий `summarize` (суммаризация текста) |
| Prompt builder | Системная инструкция + пользовательский текст в маркерах `<<< >>>` |
| Вызов LLM | Таймаут, 3 попытки, экспоненциальный backoff, fallback |
| Пост-обработка | Очистка пробелов/код-фенсов, безопасный разбор JSON, проверка на пустоту |
| Кеш | In-memory TTL-кеш, ключ из текста + модели + температуры + системного промпта |
| Наблюдаемость | JSON-логи в консоль и файл, время каждого этапа, cache hit/miss |
| Тесты | 22 теста (pytest) |
| Документация | README + `test_report.md` |

---

## Архитектура

```
Клиент (curl / Postman / браузер / CLI)
        │  POST /chat {"message": "..."}
        ▼
┌──────────────────────────────────────────────┐
│ API слой (FastAPI + Pydantic)                │
│  · валидация длины/пустоты                   │
│  · 400 при ошибке ввода                      │
└───────────────┬──────────────────────────────┘
                ▼
┌──────────────────────────────────────────────┐
│ SummarizeService (бизнес-логика)             │
│  1. build_prompt → system + user             │
│  2. cache.make_key → поиск в TTL-кеше        │
│  3. LLMClient.generate                       │
│  4. postprocess                              │
│  5. cache.set                                │
└───────────────┬──────────────────────────────┘
                ▼
┌──────────────────────────────────────────────┐
│ LLMClient                                    │
│  · timeout                                   │
│  · retries 2–3, exponential backoff + jitter │
│  · только retryable-ошибки                   │
│  · LLMUnavailableError → fallback            │
└───────────────┬──────────────────────────────┘
                ▼
┌──────────────────────────────────────────────┐
│ Provider: mock | openai | anthropic          │
└──────────────────────────────────────────────┘
```

---

## Быстрый старт

Требования: **Python 3.9+** (проверено на 3.14.5).

```bash
cd my_llm_service

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

Создайте `.env` (необязательно для режима `mock`):

```bash
cp .env.example .env
```

Запуск одной командой:

```bash
python main.py
```

Сервис поднимется на `http://127.0.0.1:8000`:

- `GET /` — простая веб-форма;
- `GET /health` — статус;
- `GET /docs` — Swagger UI;
- `POST /chat` — основной эндпоинт.

> По умолчанию используется провайдер `mock` — он работает офлайн и не требует
> API-ключа. Для реальной модели переключите провайдера (см. ниже).

### Windows: корректная кириллица в консоли

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
python main.py
```

---

## Конфигурация

Настройки лежат в `config/config.yaml`, секреты — только в `.env` / переменных
окружения. Переменные окружения имеют приоритет над YAML.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` / `openai` / `anthropic` |
| `LLM_API_KEY` | — | ключ провайдера (только в `.env`) |
| `LLM_MODEL` | `gpt-4o-mini` | имя модели |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | базовый URL API |
| `LLM_TEMPERATURE` | `0.2` | температура по умолчанию |
| `LLM_TIMEOUT_SECONDS` | `10` | таймаут одного вызова |
| `LLM_MAX_RETRIES` | `3` | число попыток |
| `LLM_BACKOFF_BASE_SECONDS` | `0.5` | база экспоненциальной задержки |
| `LLM_BACKOFF_MAX_SECONDS` | `4` | потолок задержки |
| `CACHE_TTL_SECONDS` | `600` | TTL кеша (10 минут) |
| `CACHE_MAX_ENTRIES` | `1000` | максимум записей |
| `LOG_LEVEL` | `INFO` | уровень логирования |
| `LOG_FILE` | `logs/app.log` | файл логов |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | адрес сервера |

Пример `.env`:

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=10
LLM_MAX_RETRIES=3
CACHE_TTL_SECONDS=600
```

---

## Провайдеры LLM

| Провайдер | Что делает | Нужен ключ |
|---|---|---|
| `mock` | Детерминированное «резюме» офлайн. Используется для демо и тестов, умеет имитировать сбои | нет |
| `openai` | OpenAI Chat Completions API (`/chat/completions`) | да |
| `anthropic` | Anthropic Messages API (`/messages`) | да |

Переключение:

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
```

или

```dotenv
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_BASE_URL=https://api.anthropic.com/v1
```

Ключи **никогда** не попадают в `config.yaml` и в Git: `.env` добавлен в `.gitignore`.

---

## API

### `POST /chat`

Запрос:

```json
{
  "message": "Текст для суммаризации, 1–1000 символов",
  "scenario": "summarize",
  "temperature": 0.2,
  "model": "gpt-4o-mini"
}
```

Обязательное поле — только `message`. `scenario`, `temperature`, `model` —
необязательные переопределения (участвуют в ключе кеша).

Успешный ответ `200`:

```json
{
  "request_id": "0ffd3896cfd5",
  "answer": "Краткое резюме текста...",
  "cached": false,
  "fallback": false,
  "model": "gpt-4o-mini",
  "attempts": 1,
  "elapsed_ms": 0.93
}
```

Ошибка валидации `400`:

```json
{
  "request_id": "559a31c0c17f",
  "error": {
    "code": "validation_error",
    "message": "Поле 'message': Value error, message не должно быть пустым"
  },
  "fallback": false
}
```

Модель недоступна `503` (fallback):

```json
{
  "request_id": "657dd21a16f4",
  "answer": "Сервис временно недоступен, попробуйте позже.",
  "cached": false,
  "fallback": true,
  "error": {
    "code": "llm_unavailable",
    "message": "Сервис временно недоступен, попробуйте позже."
  }
}
```

Некорректный ответ модели `502`:

```json
{
  "request_id": "…",
  "answer": "",
  "cached": false,
  "fallback": false,
  "error": {
    "code": "bad_model_response",
    "message": "Модель вернула некорректный ответ. Попробуйте ещё раз."
  }
}
```

### `GET /health`

```json
{"status":"ok","provider":"mock","model":"gpt-4o-mini","cache":{"hits":0,"misses":0,"size":0}}
```

---

## Примеры запросов

### curl (bash)

```bash
curl -s http://127.0.0.1:8000/health

curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Python — это язык программирования. Он используется в анализе данных."}'

# повторный запрос с тем же текстом → cached: true
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Python — это язык программирования. Он используется в анализе данных."}'

# ошибка валидации → 400
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":""}'
```

### PowerShell

```powershell
$body = '{"message":"Python — это язык программирования."}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

### CLI

```bash
python main.py --cli "Python — язык программирования. Он популярен в анализе данных."
```

---

## Кеширование

- Реализация: `cache/ttl_cache.py`, потокобезопасный словарь `key → (value, expires_at)`.
- Ключ: SHA-256 от канонического JSON:
  `{text, model, temperature, system_prompt, scenario, version}`.
  Поэтому изменение любого параметра даёт новый ключ.
- TTL: 600 секунд (10 минут), настраивается.
- Ограничение размера: при переполнении вытесняется запись с ближайшим истечением.
- Логи: `cache_hit` / `cache_miss` с `cache_key` и статистикой.

Проверка: два одинаковых запроса → второй возвращает `"cached": true`, а провайдер
вызывается только один раз (это проверяется тестом `test_cache_hit_on_repeated_request`).

---

## Устойчивость и ошибки

| Ситуация | Поведение |
|---|---|
| Таймаут/сеть/5xx/429 | Ретрай, всего 2–3 попытки, экспоненциальная задержка + jitter |
| 4xx (кроме 429) | Без ретраев, ошибка сразу |
| Все попытки исчерпаны | `LLMUnavailableError` → fallback-ответ, HTTP 503 |
| Невалидный JSON/структура ответа модели | Лог `invalid_json_response`, берётся очищенный текст; пустой ответ → HTTP 502 |
| Ошибка валидации входа | HTTP 400 с понятным сообщением |

Fallback-текст: `Сервис временно недоступен, попробуйте позже.`

Ретраи выполняются только для временных ошибок. Постоянные ошибки
(неверный ключ, неизвестный провайдер) не повторяются.

---

## Логирование

Формат — одна JSON-строка на событие, вывод в консоль и `logs/app.log`.

Основные события:

| Событие | Что содержит |
|---|---|
| `request_received` | `request_id`, method, path |
| `prompt_built` | system prompt, модель, температура, длина промпта |
| `cache_hit` / `cache_miss` | ключ кеша, статистика |
| `llm_call_ok` | провайдер, модель, попытка, время |
| `llm_call_failed` | код ошибки, retryable, время |
| `llm_retry_scheduled` | номер попытки, задержка |
| `llm_unavailable` | число попыток, последняя ошибка |
| `fallback_returned` | причина fallback |
| `postprocess_failed` | причина и превью ответа |
| `validation_error` | поле и текст ошибки |
| `request_completed` | статус, время выполнения |

Пример строки:

```json
{"ts":"2026-11-24T13:57:54.658055+00:00","level":"INFO","logger":"cache.ttl_cache","message":"cache_hit","cache_key":"5d6c87eae70b","cache_stats":{"hits":1,"misses":1,"size":1}}
```

---

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Покрыто:

- валидный запрос и формат ответа;
- пустое сообщение, отсутствующее поле, слишком длинный текст, неизвестный сценарий → 400;
- cache hit на повторном запросе (провайдер вызван один раз);
- изменение температуры меняет ключ кеша;
- fallback при недоступности модели → 503;
- TTL-истечение, лимит записей, статистика кеша;
- ретраи: успех после 2 сбоев, отказ после исчерпания попыток, границы backoff;
- пост-обработка: код-фенсы, извлечение JSON, невалидный JSON, пустой ответ.

Результат: **22 passed**.

---

## Демонстрация

```bash
python main.py --demo
```

Скрипт прогоняет через реальный HTTP-стек 5 сценариев:

1. корректный запрос;
2. повторный запрос → cache hit;
3. пустое сообщение → 400;
4. слишком длинный текст → 400;
5. сбой модели → fallback, 503.

Подробные результаты, логи и **ручной чек-лист из 20 пунктов** — в
[`test_report.md`](test_report.md).

---

## Структура проекта

```
my_llm_service/
├── api/                  # HTTP-слой
│   ├── middleware.py     # request_id, тайминги
│   ├── routes.py         # /chat, /health
│   └── schemas.py        # Pydantic-модели
├── services/             # бизнес-логика
│   └── summarize.py      # pipeline: prompt → cache → LLM → postprocess
├── llm/                  # работа с моделью
│   ├── client.py         # таймаут, ретраи, backoff
│   ├── errors.py         # доменные ошибки
│   ├── postprocess.py    # очистка и разбор ответа
│   ├── prompts.py        # prompt builder
│   └── providers.py      # mock / openai / anthropic
├── cache/
│   └── ttl_cache.py      # TTL-кеш + ключ
├── config/
│   ├── config.yaml       # настройки
│   ├── loader.py         # YAML + env
│   └── logging_setup.py  # JSON-логи
├── tests/                # pytest
├── main.py               # точка входа, демо, CLI
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

---

## Ограничения

- Кеш **в памяти процесса**: не разделяется между воркерами и очищается при
  рестарте. Для production — Redis.
- Провайдер `mock` не вызывает реальную модель; он нужен для офлайн-демо и тестов.
- Один сценарий (`summarize`); добавление новых — через `SCENARIOS` в `prompts.py`.
- Нет аутентификации и rate limiting — сервис учебный.
- Синхронный HTTP-клиент: FastAPI выполняет эндпоинт в threadpool. Для высокой
  нагрузки стоит перейти на `async httpx` и `async def`.
- В логах сохраняется системный промпт (не пользовательские секреты).

---

## Ссылка на репозиторий

Приватный репозиторий: <https://github.com/blackurs/my-llm-service>

Доступ выдаётся в GitHub → Settings → Collaborators (или через приглашение в
организации).
