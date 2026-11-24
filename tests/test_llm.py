"""Тесты ретраев и клиента LLM."""
from __future__ import annotations

import pytest

from config.loader import LLMConfig
from llm.client import LLMClient
from llm.errors import LLMUnavailableError
from llm.providers import MockProvider


def make_config(**overrides) -> LLMConfig:
    config = LLMConfig(
        provider="mock",
        model="test-model",
        temperature=0.0,
        timeout_seconds=1.0,
        max_retries=3,
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_retry_then_success():
    config = make_config()
    provider = MockProvider(config, fail_mode="first_n", fail_times=2)
    client = LLMClient(config, provider=provider, sleep_func=lambda _: None)

    result = client.generate(
        [{"role": "user", "content": "Первый текст. Второй текст."}]
    )

    assert result.attempts == 3
    assert provider.calls == 3
    assert result.text


def test_gives_up_after_retries():
    config = make_config(max_retries=2)
    provider = MockProvider(config, fail_mode="always")
    client = LLMClient(config, provider=provider, sleep_func=lambda _: None)

    with pytest.raises(LLMUnavailableError):
        client.generate([{"role": "user", "content": "x"}])

    assert provider.calls == 2


def test_backoff_is_bounded():
    config = make_config(
        max_retries=3, backoff_base_seconds=1.0, backoff_max_seconds=2.0
    )
    provider = MockProvider(config, fail_mode="always")
    delays: list[float] = []
    client = LLMClient(config, provider=provider, sleep_func=delays.append)

    with pytest.raises(LLMUnavailableError):
        client.generate([{"role": "user", "content": "x"}])

    assert len(delays) == 2
    assert all(delay <= 2.0 + 0.1 + 1e-9 for delay in delays)
    assert delays[1] >= delays[0]
