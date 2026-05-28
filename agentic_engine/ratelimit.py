"""Rate limiting helpers — wraps :mod:`slowapi` when present, no-op otherwise.

Use :func:`apply` once on the FastAPI app to install the limiter middleware.
Then decorate endpoints with :func:`limit("10/minute")`.

Configuration via env::

    AGENTIC_RATELIMIT_DEFAULT="60/minute"  # applied to all routes
    AGENTIC_RATELIMIT_DISABLE=1            # bypass entirely
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

try:  # pragma: no cover — optional
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    _AVAILABLE = True
except ImportError:  # pragma: no cover
    Limiter = None  # type: ignore[assignment]
    RateLimitExceeded = Exception  # type: ignore[assignment,misc]
    SlowAPIMiddleware = None  # type: ignore[assignment]
    get_remote_address = lambda req: ""  # type: ignore[assignment]  # noqa: E731
    _AVAILABLE = False


_LIMITER: Any = None


def _is_disabled() -> bool:
    return os.environ.get("AGENTIC_RATELIMIT_DISABLE") == "1" or not _AVAILABLE


def get_limiter() -> Any:
    global _LIMITER
    if _LIMITER is None and _AVAILABLE:  # pragma: no cover
        default = os.environ.get("AGENTIC_RATELIMIT_DEFAULT", "")
        kwargs = {"key_func": get_remote_address}
        if default:
            kwargs["default_limits"] = [default]
        _LIMITER = Limiter(**kwargs)
    return _LIMITER


def apply(app: Any) -> None:
    """Install the limiter on a FastAPI app. No-op when slowapi is missing."""
    if _is_disabled():
        return
    limiter = get_limiter()
    if limiter is None:  # pragma: no cover
        return
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    async def _handler(request: Any, exc: Any) -> Any:  # pragma: no cover
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=429, content={"error": "rate_limited", "detail": str(exc)})

    app.add_exception_handler(RateLimitExceeded, _handler)


def limit(rule: str) -> Callable[[Any], Any]:
    """Endpoint decorator. Falls back to identity when slowapi missing/disabled."""
    if _is_disabled():
        def _identity(fn: Any) -> Any:
            return fn

        return _identity
    return get_limiter().limit(rule)


__all__ = ["apply", "limit", "get_limiter"]
