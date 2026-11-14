"""Simple in-memory TTL response cache."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def cache_enabled_from_env() -> bool:
    """Return whether caching is enabled.

    Disabled when ``BIRDWEATHER_CACHE_ENABLED`` is ``0``/``false``/``no``/``off``,
    or when ``BIRDWEATHER_CACHE_TTL`` is ``0``.
    """
    flag = os.environ.get("BIRDWEATHER_CACHE_ENABLED")
    if flag is not None and str(flag).strip():
        if str(flag).strip().lower() in {"0", "false", "no", "off"}:
            return False
        if str(flag).strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return _env_float("BIRDWEATHER_CACHE_TTL", 60.0) > 0


def cache_ttl_from_env(default: float = 60.0) -> float:
    return max(0.0, _env_float("BIRDWEATHER_CACHE_TTL", default))


def cache_max_entries_from_env(default: int = 256) -> int:
    return max(0, _env_int("BIRDWEATHER_CACHE_MAX_ENTRIES", default))


def make_cache_key(*parts: Any) -> str:
    """Stable hash key from JSON-serializable parts."""
    payload = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TTLCache:
    """Thread-safe LRU dict with per-entry TTL."""

    def __init__(self, *, ttl_seconds: float = 60.0, max_entries: int = 256) -> None:
        self._ttl = max(0.0, float(ttl_seconds))
        self._max = max(0, int(max_entries))
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._ttl > 0 and self._max > 0

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            expires_at, value = item
            if expires_at <= now:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    @classmethod
    def from_env(cls) -> TTLCache:
        if not cache_enabled_from_env():
            return cls(ttl_seconds=0.0, max_entries=0)
        return cls(
            ttl_seconds=cache_ttl_from_env(),
            max_entries=cache_max_entries_from_env(),
        )
