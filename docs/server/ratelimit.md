# Rate limit

`agentic_engine.ratelimit` wraps [slowapi](https://github.com/laurentS/slowapi)
and is applied automatically by `agentic_engine.server`:

```python
import agentic_engine.ratelimit as ratelimit
ratelimit.apply(app)
```

## Defaults

| Env                              | Default                        |
|----------------------------------|--------------------------------|
| `AGENTIC_RATELIMIT_DEFAULT`      | `60/minute`                    |
| `AGENTIC_RATELIMIT_AUTH`         | `5/minute` (only `/auth/token`)|
| `AGENTIC_RATELIMIT_DISABLE`      | unset                          |

Set `AGENTIC_RATELIMIT_DISABLE=1` and `apply()` becomes a no-op — handy
for CI and ad-hoc tests where you'd rather hammer the server.

## Custom key function

By default, the limiter keys on `request.client.host`. Behind a proxy
that sets `X-Forwarded-For`, register the trusted-proxy middleware
upstream of `ratelimit.apply(app)` so that the limiter sees the real
caller's IP.

## When `slowapi` is missing

`apply()` logs a warning at INFO and returns. The server continues to
boot but loses per-IP throttling. Install the `[ratelimit]` extra to
get it back: `pip install "agentic-engine[ratelimit]"`.
