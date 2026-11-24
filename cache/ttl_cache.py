"""TTL-кеш в памяти с ключом из параметров запроса."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("cache.ttl_cache")


class TTLCache:
    """Потокобезопасный кеш: key -> (value, expires_at).

    TTL задаётся в секундах. Часы можно подменить (clock) для тестов.
    """

    def __init__(
        self,
        ttl_seconds: int = 600,
        max_entries: int = 1000,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self._clock = clock or time.monotonic
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------ keys
    @staticmethod
    def make_key(
        *,
        text: str,
        model: str,
        temperature: float,
        system_prompt: str,
        scenario: str,
    ) -> str:
        """Ключ учитывает текст, модель, температуру и системный промпт."""
        payload = {
            "version": 1,
            "text": text,
            "model": model,
            "temperature": round(float(temperature), 4),
            "system_prompt": system_prompt,
            "scenario": scenario,
        }
        canonical = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------- api
    def get(self, key: str) -> Optional[Any]:
        now = self._clock()
        expired = False
        with self._lock:
            item = self._store.get(key)
            if item is None:
                self._misses += 1
                value = None
            else:
                stored_value, expires_at = item
                if now >= expires_at:
                    del self._store[key]
                    self._misses += 1
                    expired = True
                    value = None
                else:
                    self._hits += 1
                    value = stored_value

        if value is None:
            logger.info(
                "cache_miss",
                extra={
                    "cache_key": key[:12],
                    "reason": "expired" if expired else "not_found",
                    "cache_stats": self.stats(),
                },
            )
        else:
            logger.info(
                "cache_hit",
                extra={"cache_key": key[:12], "cache_stats": self.stats()},
            )
        return value

    def set(self, key: str, value: Any) -> None:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            if key not in self._store and len(self._store) >= self.max_entries:
                # вытесняем запись с ближайшим истечением
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]
            self._store[key] = (value, now + self.ttl_seconds)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._store),
            }

    # -------------------------------------------------------------- internal
    def _purge_expired(self, now: float) -> None:
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for key in expired:
            del self._store[key]
