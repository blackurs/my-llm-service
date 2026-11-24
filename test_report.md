# Отчёт о тестировании

**Проект:** LLM Summarization Service (`my_llm_service`)
**Дата:** 24.11.2026
**Окружение:** Windows, Python 3.14.5, pytest 8.x, FastAPI + httpx
**Провайдер при тестировании:** `mock` (офлайн, без API-ключа)

Все результаты ниже получены реальным запуском сервиса и тестов, а не
«ожидаемым» поведением. Команды для воспроизведения указаны в каждом разделе.

---

## 1. Автотесты

```bash
pip install -r requirements-dev.txt
pytest
```

Фактический результат:

```
......................                                                   [100%]
22 passed in 0.17s
```

| Файл | Что проверяет | Тестов |
|---|---|---|
| `tests/test_api.py` | HTTP-слой: успех, кеш, 400, fallback 503, /health | 9 |
| `tests/test_cache.py` | TTL, ключ из параметров, вытеснение, статистика | 4 |
| `tests/test_llm.py` | ретраи, исчерпание попыток, границы backoff | 3 |
| `tests/test_postprocess.py` | фенсы, JSON, невалидный JSON, пустой ответ | 6 |

---

## 2. Сценарий 1 — успешный запрос

**Команда:**

```bash
python main.py --demo
```

**Запрос:**

```json
{
  "message": "Python — это высокоуровневый язык программирования. Он широко используется в анализе данных, машинном обучении и веб-разработке. Синтаксис Python считается простым для изучения. Большое сообщество поддерживает множество библиотек."
}
```

**Фактический ответ (HTTP 200):**

```json
{
  "request_id": "0ffd3896cfd5",
  "answer": "[mock-summary] Python — это высокоуровневый язык программирования. Он широко используется в анализе данных, машинном обучении и веб-разработке…",
  "cached": false,
  "fallback": false,
  "model": "gpt-4o-mini",
  "attempts": 1,
  "elapsed_ms": 0.93
}
```

**Фрагмент JSON-лога (`logs/app.log`), тот же `request_id`:**

```json
{"message":"request_received","request_id":"0ffd3896cfd5","method":"POST","path":"/chat"}
{"message":"prompt_built","request_id":"0ffd3896cfd5","scenario":"summarize","model":"gpt-4o-mini","temperature":0.2,"prompt_chars":292}
{"message":"cache_miss","cache_key":"5d6c87eae70b","reason":"not_found","cache_stats":{"hits":0,"misses":1,"size":0}}
{"message":"llm_call_ok","provider":"mock","model":"gpt-4o-mini","attempt":1,"elapsed_ms":0.15}
{"message":"request_completed","request_id":"0ffd3896cfd5","cached":false,"attempts":1,"answer_chars":144}
```

**Вывод:** pipeline отработал полностью: валидация → промпт → кеш (miss) → LLM →
пост-обработка → ответ. Время каждого этапа зафиксировано в логе.

---

## 3. Сценарий 2 — ошибка валидации

### 3.1. Пустое / пробельное сообщение

**Запрос:** `{"message": "   "}`

**Фактический ответ (HTTP 400):**

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

**Лог:**

```json
{"level":"WARNING","message":"validation_error","request_id":"559a31c0c17f","detail":"Поле 'message': Value error, message не должно быть пустым"}
{"message":"request_completed","request_id":"559a31c0c17f","method":"POST","path":"/chat","status_code":400}
```

### 3.2. Слишком длинный текст (1001 символ)

```json
{
  "request_id": "bc6bfb6ad245",
  "error": {
    "code": "validation_error",
    "message": "Поле 'message': String should have at most 1000 characters"
  },
  "fallback": false
}
```

### 3.3. Остальные проверенные случаи

| Вход | HTTP | Сообщение |
|---|---|---|
| `{}` (нет поля `message`) | 400 | `Поле 'message': Field required` |
| `{"message": "Текст", "scenario": "translate"}` | 400 | недопустимый сценарий |
| `{"message": "Текст", "temperature": 5}` | 400 | значение вне диапазона 0–2 |

**Вывод:** некорректный ввод не доходит до модели, пользователь получает
понятное сообщение с именем поля, а не 500/stack trace.

---

## 4. Сценарий 3 — сбой сети / недоступность модели

**Как воспроизведён:** в демо-скрипте провайдер заменяется на
`MockProvider(fail_mode="always")`, который на каждом вызове бросает
`LLMTimeoutError` (имитация таймаута сети). Настройки: `max_retries=3`,
`backoff_base_seconds=0.5`.

**Запрос:** `{"message": "Проверка недоступности модели."}`

**Фактический ответ (HTTP 503):**

```json
{
  "request_id": "a7fedf9273a9",
  "answer": "Сервис временно недоступен, попробуйте позже.",
  "cached": false,
  "fallback": true,
  "error": {
    "code": "llm_unavailable",
    "message": "Сервис временно недоступен, попробуйте позже."
  }
}
```

**Фактическая последовательность в логе:**

```json
{"level":"WARNING","message":"llm_call_failed","attempt":1,"max_attempts":3,"error_code":"llm_timeout","retryable":true,"error":"simulated LLM timeout"}
{"message":"llm_retry_scheduled","attempt":2,"delay_seconds":0.506}
{"level":"WARNING","message":"llm_call_failed","attempt":2,"max_attempts":3,"error_code":"llm_timeout","retryable":true}
{"message":"llm_retry_scheduled","attempt":3,"delay_seconds":1.097}
{"level":"WARNING","message":"llm_call_failed","attempt":3,"max_attempts":3,"error_code":"llm_timeout","retryable":true}
{"level":"ERROR","message":"llm_unavailable","provider":"mock","attempts":3,"last_error":"simulated LLM timeout"}
{"level":"ERROR","message":"fallback_returned","request_id":"a7fedf9273a9","error":"LLM is unavailable after 3 attempt(s): simulated LLM timeout","elapsed_ms":1604.61}
{"message":"request_completed","request_id":"a7fedf9273a9","status_code":503}
```

**Что подтверждено:**

- выполнено ровно 3 попытки;
- задержки растут экспоненциально: ~0.5 с → ~1.1 с (база 0.5 с, потолок 4 с, + jitter);
- после исчерпания попыток сервис не падает, а отдаёт fallback и HTTP 503;
- суммарное время сбоя ≈ 1.6 с, запрос не «висит».

Дополнительно тестом `test_retry_then_success` проверен обратный случай:
2 сбоя подряд → третья попытка успешна (`attempts=3`, провайдер вызван 3 раза).

---

## 5. Сценарий 4 — попадание в кеш

**Проверено на реально запущенном сервере** (`python main.py` + HTTP-запросы),
а не только через TestClient.

**Запрос №1:**

```json
{"message": "Go is a compiled language used for backend services. It is fast and simple."}
```

**Ответ №1 (HTTP 200):**

```json
{
  "request_id": "eb7674240eab",
  "answer": "[mock-summary] Go is a compiled language used for backend services. It is fast and simple.",
  "cached": false,
  "fallback": false,
  "model": "gpt-4o-mini",
  "attempts": 1,
  "elapsed_ms": 0.64
}
```

**Тот же запрос №2:** `cached = true`

**Лог двух запросов:**

```json
{"message":"cache_miss","cache_key":"c08b112d5577","reason":"not_found","cache_stats":{"hits":0,"misses":1,"size":0}}
{"message":"llm_call_ok","provider":"mock","attempt":1}
{"message":"request_completed","request_id":"eb7674240eab","cached":false,"elapsed_ms":0.64}

{"message":"cache_hit","cache_key":"c08b112d5577","cache_stats":{"hits":1,"misses":1,"size":1}}
{"message":"request_completed","request_id":"8edc95a2af17","cached":true,"elapsed_ms":0.24}
```

**Статистика кеша после серии:** `{"hits":1,"misses":1,"size":1}`

**Что подтверждено:**

- второй идентичный запрос не вызывает провайдера (`attempts=0`);
- ответ побайтово совпадает с первым;
- ключ кеша одинаковый (`c08b112d5577`), в логе есть `cache_hit`;
- изменение температуры меняет ключ: тест `test_temperature_override_changes_cache_key`
  (два запроса с `temperature` по умолчанию и `0.9` → провайдер вызван 2 раза);
- истечение TTL проверено тестом `test_ttl_expiry` (часы подменяются).

---

## 6. Пост-обработка ответа модели

| Вход | Результат | Тест |
|---|---|---|
| ` ```\n  Привет   мир \n``` ` | `Привет мир` | `test_strips_whitespace_and_code_fences` |
| `{"summary": "Краткое резюме текста."}` | `Краткое резюме текста.` | `test_extracts_json_summary` |
| ` ```json\n{"answer": "Ответ из JSON"}\n``` ` | `Ответ из JSON` | `test_json_fence_is_parsed` |
| незакрытый JSON | очищенный текст + WARNING `invalid_json_response` | `test_invalid_json_falls_back_to_cleaned_text` |
| пустая строка / `None` | `PostProcessError` → HTTP 502 | `test_empty_response_raises`, `test_none_response_raises` |

---

## 7. Ручной чек-лист

Отмечайте пункты после локального запуска. Фактический результат — из
проведённого прогона.

| # | Проверка | Как проверить | Ожидаемо | Факт |
|---|---|---|---|---|
| 1 | Установка зависимостей | `pip install -r requirements.txt` | без ошибок | ✅ |
| 2 | Запуск одной командой | `python main.py` | сервер на `127.0.0.1:8000` | ✅ |
| 3 | Health-check | `GET /health` | `{"status":"ok","provider":"mock",...}` | ✅ |
| 4 | Swagger | открыть `/docs` | UI со схемами `/chat`, `/health` | ✅ |
| 5 | Веб-форма | открыть `/` | страница с полем и кнопкой | ✅ |
| 6 | Успешный запрос | `POST /chat` с текстом | 200, непустой `answer`, `cached=false` | ✅ |
| 7 | Повторный запрос | тот же `POST /chat` | 200, `cached=true`, `attempts=0` | ✅ |
| 8 | Пустой ввод | `{"message":"   "}` | 400, `validation_error` | ✅ |
| 9 | Длинный ввод | 1001 символ | 400, «at most 1000 characters» | ✅ |
| 10 | Нет поля | `{}` | 400, «Field required» | ✅ |
| 11 | Неизвестный сценарий | `{"scenario":"translate"}` | 400 | ✅ |
| 12 | Неверная температура | `temperature=5` | 400 | ✅ |
| 13 | Сбой модели | `MockProvider(fail_mode="always")` или отключить сеть | 3 попытки, затем 503 + fallback | ✅ |
| 14 | Ретраи | `--demo` / `test_retry_then_success` | успех после 2 сбоев | ✅ |
| 15 | TTL кеша | `test_ttl_expiry` | запись исчезает после TTL | ✅ |
| 16 | Ключ кеша | изменить `temperature`/`model` | новый ключ, промах кеша | ✅ |
| 17 | JSON-логи | открыть `logs/app.log` | одна JSON-строка на событие, есть `request_id`, `elapsed_ms` | ✅ |
| 18 | Секреты | проверить репозиторий | ключа нет в `config.yaml`/коде, `.env` в `.gitignore` | ✅ |
| 19 | CLI | `python main.py --cli "Текст..."` | резюме в stdout, код возврата 0 | ✅ |
| 20 | Демо | `python main.py --demo` | 5 сценариев, статистика кеша | ✅ |

### Быстрые команды для ручной проверки

```bash
# 1. запуск
python main.py

# 2. здоровье
curl -s http://127.0.0.1:8000/health

# 3. успех + кеш
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Python — язык программирования. Он популярен в анализе данных."}'
# повторить ту же команду → "cached": true

# 4. ошибка валидации
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" -d '{"message":""}'

# 5. сбой модели (офлайн-эмуляция)
python main.py --demo
```

PowerShell:

```powershell
$body = '{"message":"Python — язык программирования."}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

---

## 8. Проверка реального провайдера (инструкция)

В отчёте использован `mock`, чтобы результат был воспроизводим без ключа и
сети. Для проверки с реальной моделью:

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

```bash
python main.py
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Python — язык программирования. Он используется в анализе данных."}'
```

Ожидаемо: `200`, осмысленное резюме на русском, `attempts=1`, в логах
`llm_call_ok` с реальным провайдером. При неверном ключе — 3 попытки не
выполняются (ошибка 401 не retryable), ответ 503 с fallback и запись
`llm_unavailable`.

---

## 9. Итог

| Требование задания | Статус |
|---|---|
| Успешный запрос (success) | ✅ подтверждён |
| Ошибка валидации | ✅ подтверждена (400 + понятное сообщение) |
| Сбой сети → fallback | ✅ подтверждён (3 попытки, backoff, 503) |
| Попадание в кеш | ✅ подтверждено (cache hit, attempts=0) |
| Таймауты и ретраи | ✅ есть и покрыты тестами |
| Пост-обработка / parse errors | ✅ есть и покрыта тестами |
| JSON-логи этапов | ✅ есть, с таймингами |
| Автотесты | ✅ 22 passed |

Сервис готов к локальному запуску и проверке. Все результаты воспроизводимы
командами из разделов выше.
