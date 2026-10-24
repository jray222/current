"""
Minimal in-process sliding-window rate limiter for sensitive auth endpoints
(login, 2FA verification, registration). This app is deployed as a single
household process, so an in-memory limiter is sufficient and avoids
pulling in Redis or another external dependency purely for this purpose.
"""
import time
import threading
from collections import defaultdict, deque
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait before trying again.",
                )
            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# 10 attempts per 5 minutes per client IP, for auth endpoints that touch
# credentials (login, 2FA verification, registration/bootstrap).
auth_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=300)


def enforce_auth_rate_limit(request: Request) -> None:
    # Imported lazily to avoid a circular import (deps -> models -> database).
    from app.deps import get_client_ip
    auth_rate_limiter.check(f"{get_client_ip(request)}:{request.url.path}")
