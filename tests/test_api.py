"""Интеграционные тесты HTTP-слоя."""
from __future__ import annotations

from llm.providers import MockProvider


def test_valid_request(client):
    response = client.post(
        "/chat",
        json={
            "message": (
                "FastAPI — это веб-фреймворк для Python. "
                "Он поддерживает асинхронность и валидацию данных."
            )
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["cached"] is False
    assert body["fallback"] is False
    assert body["model"] == "test-model"
    assert response.headers.get("X-Request-ID")


def test_cache_hit_on_repeated_request(client, app):
    payload = {
        "message": "Этот текст должен попасть в кеш и вернуться повторно."
    }
    first = client.post("/chat", json=payload)
    second = client.post("/chat", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["answer"] == second.json()["answer"]
    # Провайдер вызван ровно один раз — второй ответ из кеша.
    assert app.state.service.llm_client.provider.calls == 1


def test_empty_message_rejected(client):
    response = client.post("/chat", json={"message": "   "})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "message" in body["error"]["message"]


def test_too_long_message_rejected(client):
    response = client.post("/chat", json={"message": "x" * 1001})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_message_rejected(client):
    response = client.post("/chat", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_scenario_rejected(client):
    response = client.post(
        "/chat", json={"message": "Текст", "scenario": "translate"}
    )
    assert response.status_code == 400


def test_fallback_when_llm_is_unavailable(client, app):
    app.state.service.llm_client.provider = MockProvider(
        app.state.config.llm, fail_mode="always"
    )
    response = client.post(
        "/chat", json={"message": "Уникальный текст для проверки fallback-сценария."}
    )
    assert response.status_code == 503
    body = response.json()
    assert body["fallback"] is True
    assert "недоступен" in body["error"]["message"].lower()


def test_temperature_override_changes_cache_key(client, app):
    payload = {"message": "Один и тот же текст для проверки ключа кеша."}
    first = client.post("/chat", json=payload)
    second = client.post("/chat", json={**payload, "temperature": 0.9})

    assert first.json()["cached"] is False
    assert second.json()["cached"] is False
    assert app.state.service.llm_client.provider.calls == 2


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "mock"
    assert "cache" in body
