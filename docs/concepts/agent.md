# The agent loop

Every `Agent.run()` (and its `run_async` / `run_stream` siblings) follows
the same explicit loop:

1. **Boot** — assemble `system_prompt`, optional bootstrap memory, prior
   session history, and the user input into a chat message list.
2. **Schema dump** — convert every registered `Tool` into a JSON-schema
   tool spec (`_tool_schemas`).
3. **LLM round-trip** — call `llm.chat(...)` (or `chat_stream` for the
   streaming variants). Bailian Qwen returns either a final assistant
   message or a `tool_calls` array.
4. **Tool dispatch** — for each tool call we lookup a `Tool` by name,
   validate the args against its schema, ask the `PermissionPolicy` for
   an `allow / deny / ask` decision, then execute the callable. Output
   is truncated to `tool_result_max_chars` and fed back as a
   `tool` message.
5. **Persistence** — when `store` and `session_id` are set, every turn
   is appended atomically (`BEGIN IMMEDIATE`) to the SQLite WAL store.
6. **Loop or return** — if the model wants more tool calls and we have
   `max_turns` budget left, jump back to step 3. Otherwise return
   `AgentResult(agent, output, tool_calls, turns, raw_messages)`.

## Cancellation & retries

* The LLM client retries `transient_retries` times on the OpenAI SDK's
  retryable errors.
* Network or 429s during streaming surface as exceptions out of
  `run_stream`; the caller decides whether to swallow or re-raise.

## Async surface

```python
out = await agent.run_async("hi")

async for piece in agent.run_stream_async("tell me a story"):
    print(piece, end="", flush=True)
```

`run_async` is a thin `asyncio.to_thread` wrapper — safe for hot paths
that already hold the GIL but expensive-blocking. `run_stream_async`
runs the underlying generator in an executor and `await`s each chunk.
