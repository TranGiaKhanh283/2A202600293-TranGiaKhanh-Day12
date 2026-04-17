"""
Rate limiter — sliding window, in-process.

For a multi-replica deployment, swap the deques for Redis sorted sets:
keep `ZADD key <ts> <ts>` + `ZREMRANGEBYSCORE key -inf <ts-60>` + `ZCARD key`.
The public function `check_rate_limit` stays the same.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

_rate_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    """
    Raise 429 if `key` has already hit the configured per-minute limit.
    Called from the /ask handler with the API-key bucket id.
    """
    now = time.time()
    window = _rate_windows[key]

    while window and window[0] < now - 60:
        window.popleft()

    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )

    window.append(now)


def reset() -> None:
    """Test helper — clear all buckets."""
    _rate_windows.clear()
