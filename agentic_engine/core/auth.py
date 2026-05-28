"""Auth utilities — admin-key, H5 token, and (optional) JWT-based RBAC.

The existing token model from v0.2 is preserved (admin-key + h5-token).
New in v0.3:

- :func:`make_jwt` / :func:`verify_jwt` — HS256 JWT helpers built on
  ``python-jose`` if available, else a tiny pure-Python fallback (HMAC-SHA256
  signing, JSON header/payload).
- :class:`User` and :class:`Role` — minimal RBAC with ``admin``, ``user``,
  and ``viewer`` roles; ``has(role)`` answers whether a user satisfies a
  required role (admin > user > viewer).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


_RANK = {Role.VIEWER: 0, Role.USER: 1, Role.ADMIN: 2}


@dataclass
class User:
    id: str
    role: Role = Role.USER
    extra: dict[str, Any] | None = None

    def has(self, required: Role) -> bool:
        return _RANK[self.role] >= _RANK[required]


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _secret() -> bytes:
    sec = os.environ.get("AGENTIC_JWT_SECRET", "")
    if not sec:
        raise RuntimeError("AGENTIC_JWT_SECRET not set")
    return sec.encode()


def make_jwt(claims: dict[str, Any], expires_in: int = 3600) -> str:
    """Issue an HS256 JWT. Tries ``python-jose`` first, falls back to manual."""
    payload = dict(claims)
    payload.setdefault("iat", int(time.time()))
    payload.setdefault("exp", int(time.time()) + expires_in)
    try:  # pragma: no cover — optional
        from jose import jwt as _jwt

        return _jwt.encode(payload, _secret().decode(), algorithm="HS256")
    except ImportError:
        header = {"alg": "HS256", "typ": "JWT"}
        h = _b64u(json.dumps(header, separators=(",", ":")).encode())
        p = _b64u(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{h}.{p}".encode()
        sig = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
        return f"{h}.{p}.{_b64u(sig)}"


def verify_jwt(token: str) -> dict[str, Any]:
    """Verify HS256 JWT signature + ``exp``. Raises ``ValueError`` on failure."""
    try:  # pragma: no cover — optional
        from jose import jwt as _jwt

        return _jwt.decode(token, _secret().decode(), algorithms=["HS256"])
    except ImportError:
        try:
            h_b64, p_b64, sig_b64 = token.split(".")
        except ValueError as e:
            raise ValueError("malformed token") from e
        signing_input = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64u_decode(sig_b64)):
            raise ValueError("bad signature") from None
        payload: dict[str, Any] = json.loads(_b64u_decode(p_b64))
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("token expired") from None
        return payload


def user_from_token(token: str) -> User:
    claims = verify_jwt(token)
    return User(
        id=str(claims.get("sub", "anonymous")),
        role=Role(claims.get("role", "user")),
        extra={k: v for k, v in claims.items() if k not in {"sub", "role", "exp", "iat"}},
    )


__all__ = ["Role", "User", "make_jwt", "verify_jwt", "user_from_token"]
