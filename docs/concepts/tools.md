# Tools

A `Tool` is a Python callable plus a JSON schema. The fastest way to
register one is the decorator:

```python
from agentic_engine.core.tool import tool

@tool(
    name="weather",
    description="Get current weather for a city.",
    requires_approval=False,
)
def weather(city: str, units: str = "metric") -> str:
    ...
```

The decorator inspects the function signature to build the schema —
defaults become non-required parameters; type hints become JSON types.

## Built-ins

| Name        | What it does                                          |
|-------------|-------------------------------------------------------|
| `bash_run`  | Sandboxed shell execution (rlimit + cwd allowlist).   |
| `read_file` | UTF-8 text read with size cap.                        |
| `write_file`| Backup-on-overwrite, refuses outside `cwd` allowlist. |
| `list_dir`  | `os.scandir` wrapper with depth cap.                  |
| `grep_text` | `re` over text, line-anchored hit list.               |
| `web_fetch` | `httpx.get` with size + timeout caps.                 |

## Plugin tools

Third-party packages can register tools by exposing a `Tool` (or a
factory returning one) through the `agentic_engine.tools` entry-point
group:

```toml
# pyproject.toml of an external package
[project.entry-points."agentic_engine.tools"]
my_tool = "my_pkg.tools:my_tool"
```

`agentic_engine.plugins.load_plugins()` is called by the server's
lifespan and by CLI commands; the returned tools can be passed straight
into `Agent(tools=...)`.

## Permission gating

Every dispatch consults the active `PermissionPolicy`:

* `allow` — execute silently.
* `deny`  — return `[refused]` to the model and continue.
* `ask`   — invoke `approval_hook(tool_name, args)`. The hook can call
  `policy.remember(tool_name, "allow")` to skip future prompts.
