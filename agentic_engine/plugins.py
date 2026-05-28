"""Plugin loader — discovers third-party tools via Python entry points.

Any package that ships a section like::

    [project.entry-points."agentic_engine.tools"]
    jira_search = "my_pkg.jira:search"

will have ``my_pkg.jira:search`` (which must be a callable returning a
:class:`agentic_engine.core.tool.Tool`) loaded by :func:`load_plugins`.

Built-in tools are *not* registered through entry-points; this is purely a
third-party expansion path. Failures load are logged but never raised.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import entry_points

from .core.tool import Tool

logger = logging.getLogger(__name__)


def _load_group(group: str) -> list[Tool]:
    out: list[Tool] = []
    eps = entry_points()
    selected = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])  # type: ignore[attr-defined]
    for ep in selected:
        try:
            obj: Callable[[], Tool] | Tool = ep.load()
            tool = obj() if callable(obj) and not isinstance(obj, Tool) else obj  # type: ignore[arg-type]
            if isinstance(tool, Tool):
                out.append(tool)
            else:  # pragma: no cover
                logger.debug("plugin %s did not return a Tool instance", ep.name)
        except Exception as e:  # noqa: BLE001
            logger.warning("failed to load plugin %s: %s", ep.name, e)
    return out


def load_plugins() -> list[Tool]:
    """Return all third-party tools discovered via entry points."""
    return _load_group("agentic_engine.tools")


__all__ = ["load_plugins"]
