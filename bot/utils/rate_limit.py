"""
Per-user rate limiting primitives.

Used to throttle:
  - search requests
  - reports (also enforced by DB cooldown)
  - general messages during a chat (avoid spam)
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List


class RateLimiter:
    def __init__(self) -> None:
        # key -> list[int unix seconds]
        self._hits: Dict[int, List[float]] = defaultdict(list)

    def hit(self, key: int, max_per_window: int, window_seconds: int) -> bool:
        """Record a hit. Returns True if the action is allowed, False if rate-limited."""
        now = time.time()
        bucket = self._hits[key]
        cutoff = now - window_seconds
        # drop old
        self._hits[key] = [t for t in bucket if t > cutoff]
        if len(self._hits[key]) >= max_per_window:
            return False
        self._hits[key].append(now)
        return True

    def check_only(self, key: int, max_per_window: int, window_seconds: int) -> bool:
        """Check without recording a hit."""
        now = time.time()
        bucket = self._hits.get(key, [])
        cutoff = now - window_seconds
        recent = [t for t in bucket if t > cutoff]
        return len(recent) < max_per_window

    def clear(self, key: int) -> None:
        self._hits.pop(key, None)


# shared singletons
search_limiter = RateLimiter()  # search throttle
message_limiter = RateLimiter()  # per-minute message throttle during chats
