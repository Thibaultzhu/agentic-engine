# Permissions

`PermissionPolicy` is an ordered list of `Rule` objects with a default
decision. The first match wins.

```python
from agentic_engine import PermissionPolicy, Rule

pol = PermissionPolicy(
    rules=[
        Rule(tool="bash_run",  decision="deny",  args={"command": "rm -rf *"}),
        Rule(tool="web_fetch", decision="allow", args={"url": "https://example.com/*"}),
        Rule(tool="write_*",   decision="ask"),
    ],
    default="ask",
)
pol.decide("bash_run", {"command": "rm -rf tmp"})  # -> "deny"
pol.decide("web_fetch", {"url": "https://example.com/x"})  # -> "allow"
```

## Glob semantics

* `tool` and every value in `args` use `fnmatch.fnmatchcase`.
* All listed `args` must match for the rule to fire (logical AND).
* Missing args count as a non-match — keep your patterns explicit.

## Persistence

```python
from pathlib import Path
import json
Path("perms.json").write_text(json.dumps(pol.to_dict()))
pol2 = PermissionPolicy.from_file("perms.json")
```

The default location is `${AGENTIC_HOME}/permissions.json`, picked up
automatically by `default_policy()`.

## Session-level memory

`pol.remember("bash_run", "allow")` makes every future `bash_run`
auto-approved for the lifetime of this `PermissionPolicy` instance.
Useful when an interactive approval hook offers a "remember this
choice" button.
