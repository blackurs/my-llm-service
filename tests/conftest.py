"""Общие фикстуры для тестов."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config.loader import load_config
from main import create_app


@pytest.fixture()
def app():
    config = load_config()
    # Тесты не должны ходить в реальную сеть.
    config.llm.provider = "mock"
    config.llm.model = "test-model"
    config.llm.api_key = ""
    config.llm.max_retries = 2
    config.llm.backoff_base_seconds = 0.0
    config.llm.backoff_max_seconds = 0.0
    config.cache.ttl_seconds = 600
    config.logging.level = "WARNING"
    config.logging.file = "logs/test.log"
    return create_app(config)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
