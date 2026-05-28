"""Tool — a callable an Agent can invoke. Decorator-based registration.

Schema is inferred from type hints. Supported:
    str, int, float, bool, None
    list[T], list, tuple[T, ...]            → array (with `items` when T known)
    dict[K, V], dict                        → object (with additionalProperties)
    Optional[T]  /  T | None                → schema for T (parameter is not required if default given)
    Union[A, B]  /  A | B                   → anyOf
    Literal["a", "b"]                       → enum
    Annotated[T, "free-text description"]   → schema for T, description="..."
    docstring `Args:` block (Google style)  → fills missing descriptions

Anything unknown falls back to {"type": "string", "description": "..."}.
"""
from __future__ import annotations

import inspect
import re
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin, get_type_hints

_PY_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    type(None): "null",
}


def _is_optional(tp: Any) -> tuple[bool, Any]:
    """Return (is_optional, inner_type). inner_type is the non-None branch."""
    origin = get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) < len(get_args(tp)):
            if len(args) == 1:
                return True, args[0]
            return True, typing.Union[tuple(args)]  # noqa: UP007
    return False, tp


def _type_to_schema(tp: Any) -> dict[str, Any]:
    # Annotated[T, "desc"]
    if get_origin(tp) is typing.Annotated:
        args = get_args(tp)
        base = args[0]
        desc = next((a for a in args[1:] if isinstance(a, str)), None)
        sch = _type_to_schema(base)
        if desc and "description" not in sch:
            sch["description"] = desc
        return sch

    # Optional / None handling
    is_opt, inner = _is_optional(tp)
    if is_opt and inner is not tp:
        return _type_to_schema(inner)

    origin = get_origin(tp)
    args = get_args(tp)

    # Literal[...]
    if origin is typing.Literal:
        # Pick a primitive json type from the first literal value.
        first = args[0] if args else ""
        return {"type": _PY_TO_JSON.get(type(first), "string"), "enum": list(args)}

    # Union[A, B, ...]
    if origin in (typing.Union, types.UnionType):
        return {"anyOf": [_type_to_schema(a) for a in args]}

    # list[T] / list
    if origin in (list, list) or tp is list:
        if args:
            return {"type": "array", "items": _type_to_schema(args[0])}
        return {"type": "array"}

    # tuple[T, ...] / tuple
    if origin in (tuple, tuple) or tp is tuple:
        if args:
            return {"type": "array", "items": _type_to_schema(args[0])}
        return {"type": "array"}

    # dict[K, V] / dict
    if origin in (dict, dict) or tp is dict:
        if args and len(args) == 2:
            return {"type": "object", "additionalProperties": _type_to_schema(args[1])}
        return {"type": "object"}

    # Primitives
    if tp in _PY_TO_JSON:
        return {"type": _PY_TO_JSON[tp]}

    # Unknown → string fallback
    return {"type": "string"}


_GOOGLE_ARGS_RE = re.compile(r"(?:Args|Arguments|Parameters):\s*\n(.*?)(?:\n\s*\n|\n[A-Z][a-z]+:|$)", re.DOTALL)
_PARAM_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:\s*(.+?)\s*$")


def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Return (summary, {param: description}) from a Google-style docstring."""
    if not doc:
        return "", {}
    summary = doc.strip().splitlines()[0].strip()
    descs: dict[str, str] = {}
    m = _GOOGLE_ARGS_RE.search(doc)
    if m:
        block = m.group(1)
        current_key: str | None = None
        for line in block.splitlines():
            pm = _PARAM_LINE_RE.match(line)
            if pm:
                current_key, current_desc = pm.group(1), pm.group(2).strip()
                descs[current_key] = current_desc
            elif current_key and line.strip():
                descs[current_key] += " " + line.strip()
    return summary, descs


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
    """Decorator: turn a Python function into a Tool."""

    def decorator(fn: Callable[..., Any]) -> Tool:
        tool_name = name or fn.__name__
        summary, doc_params = _parse_docstring(fn.__doc__ or "")
        tool_desc = description or summary or tool_name

        sig = inspect.signature(fn)
        try:
            hints = get_type_hints(fn, include_extras=True)
        except Exception:
            hints = {}

        properties: dict[str, Any] = {}
        required: list[str] = []
        for pname, param in sig.parameters.items():
            if pname in ("self", "cls"):
                continue
            ptype = hints.get(pname, str)
            schema = _type_to_schema(ptype)
            # Description precedence: Annotated > docstring > parameter name.
            if "description" not in schema:
                schema["description"] = doc_params.get(pname, pname)
            properties[pname] = schema
            if param.default is inspect.Parameter.empty:
                required.append(pname)
            else:
                # JSON-Schema "default"
                if param.default is not None:
                    try:
                        # Only embed json-serialisable defaults
                        import json
                        json.dumps(param.default)
                        schema["default"] = param.default
                    except Exception:
                        pass

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
