"""Структурированное JSON-логирование (консоль + файл)."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Set

from config.loader import PROJECT_ROOT, LoggingConfig

_RESERVED: Set[str] = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
}

_HANDLER_MARKER = "_llm_service_handler"


def _json_default(value: Any) -> str:
    return str(value)


class JsonFormatter(logging.Formatter):
    """Превращает каждую запись лога в одну JSON-строку."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=_json_default)


def setup_logging(config: LoggingConfig) -> None:
    """Идемпотентно настраивает root-логгер: консоль + файл."""
    root = logging.getLogger()

    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
            handler.close()

    root.setLevel(getattr(logging, config.level.upper(), logging.INFO))

    formatter = JsonFormatter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    setattr(console, _HANDLER_MARKER, True)
    root.addHandler(console)

    log_path = Path(config.file)
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    setattr(file_handler, _HANDLER_MARKER, True)
    root.addHandler(file_handler)
