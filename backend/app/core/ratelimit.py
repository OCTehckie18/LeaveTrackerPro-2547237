"""Tiny in-memory fixed-window limiter. Valid for ONE API instance (documented limitation);
swap for Redis/Upstash when scaling out."""

import threading
import time

from app.domain.errors import RateLimited


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, key: str, *, limit: int, window_s: int, message: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 10_000:  # bound memory under a flood of distinct keys
                self._hits = {k: v for k, v in self._hits.items() if now - v[0] < window_s}
            start, count = self._hits.get(key, (now, 0))
            if now - start >= window_s:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)
            if count > limit:
                raise RateLimited(message, retry_after=max(1, int(window_s - (now - start))))


limiter = FixedWindowLimiter()
