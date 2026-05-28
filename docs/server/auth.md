# JWT auth

`AGENTIC_JWT_SECRET` (≥32 random bytes) turns on HS256 JWT issuance.

## Issue a token

```bash
curl -X POST http://127.0.0.1:8765/auth/token \
  -H "X-Admin-Key: $AGENTIC_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"sub": "alice", "role": "user", "expires_in": 3600}'
# -> { "token": "eyJhbGciOi...", "expires_in": 3600 }
```

* `sub` is the user identifier echoed back by `/me`.
* `role` ∈ `{admin, user, viewer}` — drives `require_role(...)` checks.
* `expires_in` is in seconds; the token's `exp` claim is set to
  `now + expires_in`.

## Use the token

```bash
TOKEN=eyJhbGciOi...
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/me
# -> { "id": "alice", "role": "user", "exp": 1748... }
```

`require_auth` accepts:

1. `Authorization: Bearer <jwt>` — verified with `verify_jwt`.
2. `X-Admin-Key: <key>` — equal-time compare against `AGENTIC_ADMIN_KEY`.
3. `?token=<h5-token>` — short-lived UI token.

## Rotation

There is no built-in revocation list — keep `expires_in` short (≤24h)
and rotate `AGENTIC_JWT_SECRET` to invalidate every outstanding token
at once.

## Optional `python-jose`

If `python-jose[cryptography]` is installed it is used; otherwise we
fall back to a hand-rolled HMAC-SHA256 implementation that produces
identical tokens. The fallback is constant-time on signature compare.
