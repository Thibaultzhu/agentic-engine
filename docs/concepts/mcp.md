# MCP bridge

The `agentic_engine.core.mcp` and `agentic_engine.core.mcp_http`
modules talk to remote tools that follow the
[Model Context Protocol](https://modelcontextprotocol.io/) spec.

## stdio transport (`MCPClient`)

```python
from agentic_engine import MCPClient

client = MCPClient.spawn(["npx", "-y", "@org/some-mcp-server"])
client.initialize(client_name="agentic-engine", client_version="0.3.0")

for t in client.list_tools():
    print(t.name, t.description)
```

`client.as_tools()` yields `Tool` wrappers that can be passed straight
into `Agent(tools=...)`. Each wrapper validates JSON-schema args,
converts the result into a string, and surfaces `MCPError` to the
permission gate.

## HTTP / SSE transport (`MCPHTTPClient`)

For remote MCP servers exposed over JSON-RPC + Server-Sent Events:

```python
from agentic_engine.core.mcp_http import MCPHTTPClient

client = MCPHTTPClient(base_url="https://mcp.example.com",
                      headers={"Authorization": "Bearer ..."})
client.initialize()
tools = client.as_tools()
```

The class deliberately mirrors `MCPClient`'s public surface so callers
can swap implementations.

## Schema sanitisation

Both clients run incoming tool schemas through a small sanitiser that
strips JSON-schema keywords Bailian's tool-call format does not
support (`anyOf`, `allOf`, `if/then/else`, etc.) while preserving the
property name space — see `mcp.py::sanitize_schema`.
