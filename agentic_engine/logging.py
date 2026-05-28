"""Structured logging.

Wraps either :mod:`structlog` (preferred when installed) or the stdlib
:mod:`logging` module and exposes a single ``get_logger`` factory that
lets callers attach key/value context (``agent_name``, ``session_id``,
``tool_call_id`` …) without depending on the optional dependency.

Usage::

    from agentic_engine.logging import get_logger
    log = get_logger(__name__).bind(agent="planner", session="abc123")
    log.info("dispatching", tool="bash")
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

try:  # pragma: no cover — optional
    import structlog as _structlog

    _STRUCTLOG = True
except ImportError:  # pragma: no cover
    _structlog = None  # type: ignore[assignment]
    _STRUCTLOG = False


_CONFIGURED = False


def _configure_stdlib(level: int) -> None:
    """Configure stdlib logging once with a sensible default formatter."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)


class _StdLibAdapter(logging.LoggerAdapter):  # type: ignore[type-arg]
    """Make stdlib loggers expose a structlog-like ``.bind()`` API."""

    def bind(self, **extra: Any) -> _StdLibAdapter:
        merged = {**(self.extra or {}), **extra}
        return _StdLibAdapter(self.logger, merged)

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Render extra kv pairs after the message: "msg key=value key=value"
        if self.extra:
            tail = " ".join(f"{k}={v!r}" for k, v in self.extra.items())
            msg = f"{msg} {tail}"
        return msg, kwargs


def configure(level: str | int | None = None) -> None:
    """Configure logging once.

    Reads ``AGENTIC_LOG_LEVEL`` (default ``INFO``). Safe to call repeatedly.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    if level is None:
        level = os.environ.get("AGENTIC_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    if _STRUCTLOG:
        _structlog.configure(
            processors=[
                _structlog.contextvars.merge_contextvars,
                _structlog.processors.add_log_level,
                _structlog.processors.TimeStamper(fmt="iso"),
                _structlog.processors.StackInfoRenderer(),
                _structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
            ],
            wrapper_class=_structlog.make_filtering_bound_logger(level),
            cache_logger_on_first_use=True,
        )
    _configure_stdlib(level)
    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    """Return a logger that supports ``.bind(**kwargs)`` regardless of backend."""
    configure()
    if _STRUCTLOG:
        return _structlog.get_logger(name) if name else _structlog.get_logger()
    return _StdLibAdapter(logging.getLogger(name or "agentic_engine"), {})


__all__ = ["configure", "get_logger"]
