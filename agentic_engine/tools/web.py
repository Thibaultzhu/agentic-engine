"""Web fetch tool — minimal HTTP GET wrapper."""
from __future__ import annotations

import httpx

from ..core.tool import tool


@tool(name="web_fetch", description="HTTP GET a URL and return text body.", read_only=True)
def web_fetch(url: str, timeout: float = 15.0, max_chars: int = 8000) -> str:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.text[:max_chars]
    except Exception as e:  # noqa: BLE001
        return f"[error] {type(e).__name__}: {e}"
