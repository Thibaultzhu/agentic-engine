# Plugins

Third-party tools register themselves through Python entry points so
you can ship a `pip install my-agentic-extension` and have its tools
appear automatically.

## Author a plugin

```toml
# pyproject.toml of your extension package
[project]
name = "my-agentic-extension"
version = "0.1.0"
dependencies = ["agentic-engine>=0.3"]

[project.entry-points."agentic_engine.tools"]
weather = "my_pkg.tools:weather"
forecast = "my_pkg.tools:forecast"
```

```python
# my_pkg/tools.py
from agentic_engine.core.tool import tool

@tool(name="weather", description="Current weather for a city.")
def weather(city: str, units: str = "metric") -> str:
    ...
```

The exported object can be either a `Tool` instance or any callable
decorated with `@tool` — the loader unwraps both.

## Discover & use

```python
from agentic_engine.plugins import load_plugins
from agentic_engine import Agent

plugins = load_plugins()                      # iterable of Tool
agent = Agent(name="ops", tools=list(plugins))
```

`load_plugins()` swallows individual import failures, logs a warning,
and continues — one broken extension never crashes the host.

## Naming conventions

* `name=` should be a stable, human-readable verb (`weather`, not
  `my_pkg_weather_v2`). Conflicts with the same name silently drop the
  later registration.
* Tools that mutate the file system or hit external services should
  set `requires_approval=True` so the permission gate engages by
  default.
