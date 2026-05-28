"""Optional OpenTelemetry integration — best-effort, no-op when SDK missing.

If ``opentelemetry-sdk`` is installed and the env var ``OTEL_EXPORTER_OTLP_ENDPOINT``
(or ``OTEL_ENABLE=1``) is set, ``setup_tracing()`` will install a global tracer
provider exporting OTLP. Otherwise everything degrades to no-op spans so call
sites can be unconditional.
"""
from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_PROVIDER_INSTALLED = False


def _is_enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get("OTEL_ENABLE"))


def setup_tracing(service_name: str = "agentic-engine") -> bool:
    """Install a global OTLP tracer provider if SDK is present and enabled.

    Returns ``True`` if tracing was actually configured, ``False`` otherwise.
    Safe to call repeatedly.
    """
    global _PROVIDER_INSTALLED
    if _PROVIDER_INSTALLED:
        return True
    if not _is_enabled():
        return False
    try:  # pragma: no cover — optional
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        _PROVIDER_INSTALLED = True
        return True
    except Exception:  # pragma: no cover
        return False


def _get_tracer() -> Any:
    try:
        from opentelemetry import trace

        return trace.get_tracer("agentic_engine")
    except Exception:
        return None


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    """Context manager that opens a span if OTel is available, else no-op."""
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as sp:
        for k, v in attrs.items():
            with contextlib.suppress(Exception):
                sp.set_attribute(k, v)
        yield sp


__all__ = ["setup_tracing", "span"]
