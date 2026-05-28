# Logging & telemetry

## Structured logging

```python
from agentic_engine.logging import configure, get_logger

configure(level="INFO")
log = get_logger(__name__).bind(agent="planner", session="abc123")
log.info("dispatching tool", tool="bash_run")
```

* When [structlog](https://www.structlog.org/) is installed, output is
  rendered with `ConsoleRenderer` (colours auto-detected) including the
  bound key/value context.
* Otherwise, the stdlib `logging.Logger` is wrapped in `_StdLibAdapter`
  so the same `.bind(...)` API works — context is appended to the
  message body.

Tweak via env:

| Env                  | Effect                                  |
|----------------------|-----------------------------------------|
| `AGENTIC_LOG_LEVEL`  | `DEBUG` / `INFO` (default) / `WARNING`  |

## OpenTelemetry tracing

```python
from agentic_engine.telemetry import setup_tracing, span

setup_tracing("agentic-engine")          # idempotent, no-op without SDK
with span("agent.run", agent_name="planner") as sp:
    ...
```

Triggers:

| Env                          | Behaviour                                  |
|------------------------------|--------------------------------------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT`| Install OTLP exporter pointing here.       |
| `OTEL_ENABLE=1`              | Force-install the SDK even without endpoint. |

When `opentelemetry-sdk` isn't installed the function is a no-op and
`span()` yields `None`, so call sites can be unconditional. The server
already wraps `/chat` and `/dev-team` in spans tagged with
`agent_name`, `session_id`, and `model`.
