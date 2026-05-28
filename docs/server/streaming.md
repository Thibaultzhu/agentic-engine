# Streaming — SSE & WebSocket

## SSE: `POST /chat/stream`

```bash
curl -N -H "X-Admin-Key: $AGENTIC_ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"message":"Tell me a haiku about FastAPI."}' \
     http://127.0.0.1:8765/chat/stream
```

Each chunk is a single line:

```text
data: tokens streamed back...
data: more tokens...
data: [DONE]
```

Newlines inside a chunk are escaped as `\n` (CommonMark MUST not break
the SSE framing). Disconnects are clean — the underlying generator is
GC'd by Starlette.

## WebSocket: `/ws/chat`

```python
import json, asyncio, websockets

async def main():
    uri = ("ws://127.0.0.1:8765/ws/chat"
           f"?admin_key={ADMIN}")
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"message": "Tell me a joke."}))
        async for raw in ws:
            ev = json.loads(raw)
            if ev["type"] == "delta":
                print(ev["content"], end="", flush=True)
            elif ev["type"] == "done":
                break

asyncio.run(main())
```

Auth knobs (in order of preference):

1. `?token=<jwt>` query param — short-lived bearer.
2. `?admin_key=<key>` — long-lived admin key.
3. Open mode — only when neither env var is set.

The server emits four event kinds:

| `type`    | Payload                          |
|-----------|----------------------------------|
| `delta`   | `{ content: "..." }`             |
| `tool`    | `{ name, args, result }` *(future)* |
| `done`    | `{}`                             |
| `error`   | `{ detail: "..." }`              |
