"""Web fetch tool — minimal HTTP GET wrapper with SSRF guards."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from ..core.tool import tool

_BLOCKED_HOSTNAMES = {
    "metadata.google.internal",   # GCP metadata
    "metadata",                   # GCP short
    "metadata.azure.com",         # Azure metadata
}


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True   # unknown/garbage: block
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local       # 169.254.0.0/16  (AWS/Azure metadata)
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _ssrf_check(url: str) -> str | None:
    """Return error message if URL must be blocked, else None."""
    try:
        parsed = urlparse(url)
    except Exception as e:  # noqa: BLE001
        return f"bad URL: {e}"
    if parsed.scheme not in ("http", "https"):
        return f"only http(s) URLs allowed (got {parsed.scheme!r})"
    host = parsed.hostname
    if not host:
        return "URL has no host"
    if host.lower() in _BLOCKED_HOSTNAMES:
        return f"hostname {host!r} is in the metadata-service block list"
    # Resolve all addresses; refuse if any maps to a private/loopback range.
    try:
        infos = socket.getaddrinfo(host, parsed.port, proto=socket.IPPROTO_TCP)
    except Exception as e:  # noqa: BLE001
        return f"DNS resolution failed: {e}"
    for _fam, _, _, _, addr in infos:
        ip_str = addr[0]
        if _is_blocked_ip(ip_str):
            return f"resolved to blocked address {ip_str} (private/loopback/link-local)"
    return None


@tool(name="web_fetch", description="HTTP GET a URL and return text body.", read_only=True)
def web_fetch(
    url: str,
    timeout: float = 15.0,
    max_chars: int = 8000,
    allow_private: bool = False,
) -> str:
    """Fetch a URL.

    Args:
        url: http(s) URL to GET.
        timeout: Request timeout (seconds).
        max_chars: Truncate response body to this many chars.
        allow_private: If True, skip SSRF check (use for explicit local-dev fetches).
    """
    if not allow_private:
        err = _ssrf_check(url)
        if err:
            return f"[refused] {err}"
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.text[:max_chars]
    except Exception as e:  # noqa: BLE001
        return f"[error] {type(e).__name__}: {e}"
