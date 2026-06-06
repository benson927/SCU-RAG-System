import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from backend.config import get_settings


class SlidingWindowRateLimiter:
    def __init__(self):
        self._events = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(events[0] + window_seconds - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="請求過於頻繁，請稍後再試。",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


_rate_limiter = SlidingWindowRateLimiter()


def _client_key(request: Request, scope: str) -> str:
    host = request.client.host if request.client else "unknown"
    if get_settings().trust_proxy_headers:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            host = forwarded_for.split(",", 1)[0].strip() or host
    return f"{scope}:{host}"


def enforce_admin_login_rate_limit(request: Request) -> None:
    settings = get_settings()
    _rate_limiter.check(
        _client_key(request, "admin-login"),
        settings.admin_login_rate_limit,
        settings.rate_limit_window_seconds,
    )


def enforce_rag_rate_limit(request: Request) -> None:
    settings = get_settings()
    _rate_limiter.check(
        _client_key(request, "rag"),
        settings.rag_rate_limit,
        settings.rate_limit_window_seconds,
    )


def reset_rate_limits() -> None:
    _rate_limiter.clear()
