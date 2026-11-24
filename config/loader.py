"""Конфигурация сервиса: dataclasses + загрузка YAML и переменных окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


@dataclass
class LLMConfig:
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    temperature: float = 0.2
    timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 4.0


@dataclass
class CacheConfig:
    ttl_seconds: int = 600
    max_entries: int = 1000


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/app.log"


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


def _env(name: str, default: Any) -> Any:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def load_config(path: Optional[str] = None) -> AppConfig:
    """Загружает config.yaml и накладывает переменные окружения.

    Секреты (API-ключ) живут только в .env / переменных окружения и никогда
    не хранятся в config.yaml и в репозитории.
    """
    load_dotenv(PROJECT_ROOT / ".env")

    config_path = Path(
        path or os.getenv("SERVICE_CONFIG") or DEFAULT_CONFIG_PATH
    ).resolve()
    raw = _read_yaml(config_path)

    llm_raw = raw.get("llm") or {}
    cache_raw = raw.get("cache") or {}
    server_raw = raw.get("server") or {}
    logging_raw = raw.get("logging") or {}

    llm = LLMConfig(
        provider=str(_env("LLM_PROVIDER", llm_raw.get("provider", "mock"))),
        model=str(_env("LLM_MODEL", llm_raw.get("model", "gpt-4o-mini"))),
        base_url=str(_env("LLM_BASE_URL", llm_raw.get("base_url", ""))),
        api_key=str(_env("LLM_API_KEY", "")),
        temperature=float(_env("LLM_TEMPERATURE", llm_raw.get("temperature", 0.2))),
        timeout_seconds=float(
            _env("LLM_TIMEOUT_SECONDS", llm_raw.get("timeout_seconds", 10))
        ),
        max_retries=int(_env("LLM_MAX_RETRIES", llm_raw.get("max_retries", 3))),
        backoff_base_seconds=float(
            _env(
                "LLM_BACKOFF_BASE_SECONDS",
                llm_raw.get("backoff_base_seconds", 0.5),
            )
        ),
        backoff_max_seconds=float(
            _env(
                "LLM_BACKOFF_MAX_SECONDS",
                llm_raw.get("backoff_max_seconds", 4.0),
            )
        ),
    )

    cache = CacheConfig(
        ttl_seconds=int(
            _env("CACHE_TTL_SECONDS", cache_raw.get("ttl_seconds", 600))
        ),
        max_entries=int(
            _env("CACHE_MAX_ENTRIES", cache_raw.get("max_entries", 1000))
        ),
    )

    server = ServerConfig(
        host=str(_env("HOST", server_raw.get("host", "127.0.0.1"))),
        port=int(_env("PORT", server_raw.get("port", 8000))),
    )

    log = LoggingConfig(
        level=str(_env("LOG_LEVEL", logging_raw.get("level", "INFO"))),
        file=str(_env("LOG_FILE", logging_raw.get("file", "logs/app.log"))),
    )

    return AppConfig(llm=llm, cache=cache, server=server, logging=log)
