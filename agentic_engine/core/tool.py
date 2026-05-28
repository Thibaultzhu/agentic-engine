"""Tool — a callable an Agent can invoke. Decorator-based registration."""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints


_PY_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    read_only: bool = False
    requires_approval: bool = False

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    def __call__(self, **kwargs: Any) -> Any:
        return self.handler(**kwargs)


_REGISTRY: dict[str, Tool] = {}


def tool(
    name: str | None = None,
    description: str | None = None,
    read_only: bool = False,
    requires_approval: bool = False,
) -> Callable[[Callable[..., Any]], Tool]:
    """Decorator: turn a Python function into a Tool. Schema inferred from type hints + docstring."""

    def decorator(fn: Callable[..., Any]) -> Tool:
        tool_name = name or fn.__name__
        doc = (description or fn.__doc__ or "").strip().splitlines()
        tool_desc = doc[0] if doc else tool_name

        sig = inspect.signature(fn)
        try:
            hints = get_type_hints(fn)
        except Exception:
            hints = {}
        properties: dict[str, Any] = {}
        required: list[str] = []
        for pname, param in sig.parameters.items():
            if pname in ("self", "cls"):
                continue
            ptype = hints.get(pname, str)
            json_type = _PY_TO_JSON.get(ptype, "string")
            properties[pname] = {"type": json_type, "description": pname}
            if param.default is inspect.Parameter.empty:
                required.append(pname)

        params = {"type": "object", "properties": properties, "required": required}
        t = Tool(
            name=tool_name,
            description=tool_desc,
            handler=fn,
            parameters=params,
            read_only=read_only,
            requires_approval=requires_approval,
        )
        _REGISTRY[tool_name] = t
        return t

    return decorator


def registry() -> dict[str, Tool]:
    return dict(_REGISTRY)


def get(name: str) -> Tool | None:
    return _REGISTRY.get(name)
