# HTTP API

Boot the server with:

```bash
uvicorn agentic_engine.server:app --host 127.0.0.1 --port 8765
```

## Endpoints

| Method  | Path                            | Auth        | Notes                            |
|---------|---------------------------------|-------------|----------------------------------|
| `GET`   | `/health`                       | none        | `{ ok, version, ts }`            |
| `POST`  | `/chat`                         | required    | sync turn, OTel-spanned          |
| `POST`  | `/chat/stream`                  | required    | SSE `text/event-stream`          |
| WS      | `/ws/chat`                      | required    | bidirectional streaming          |
| `POST`  | `/dev-team`                     | required    | sync or `?async=1`               |
| `GET`   | `/jobs/{id}`                    | required    | dev-team async result            |
| `GET`   | `/usage`                        | required    | UsageTracker dump                |
| `GET`   | `/sessions`                     | required    | list sessions                    |
| `POST`  | `/sessions`                     | required    | create                           |
| `GET`   | `/sessions/{sid}`               | required    | messages                         |
| `POST`  | `/sessions/{sid}/append`        | required    | append a turn                    |
| `GET`   | `/cron`                         | required    | list jobs                        |
| `POST`  | `/cron`                         | required    | create job                       |
| `DELETE`| `/cron/{id}`                    | required    | delete                           |
| `POST`  | `/cron/{id}/enable`             | required    | enable                           |
| `POST`  | `/cron/{id}/disable`            | required    | disable                          |
| `GET`   | `/cron/{id}/runs`               | required    | retry / DLQ history              |
| `POST`  | `/h5/token`                     | admin only  | issue ephemeral H5 token         |
| `GET`   | `/h5/page`                      | h5-token    | static SPA shell                 |
| `POST`  | `/auth/token`                   | admin only  | issue HS256 JWT                  |
| `GET`   | `/me`                           | bearer JWT  | introspect current token         |
| `POST`  | `/eval`                         | required    | run an `evals/golden/*.json` set |

## Auth surface

* **Open mode** — neither `AGENTIC_ADMIN_KEY` nor `AGENTIC_JWT_SECRET`
  set; every endpoint accepts any caller. Fine for unit tests, never
  for production.
* **Admin-key** — set `AGENTIC_ADMIN_KEY=…`; clients pass
  `X-Admin-Key: …`.
* **JWT** — set `AGENTIC_JWT_SECRET=…` (≥32 bytes recommended) and
  hit `/auth/token` with the admin key to mint short-lived bearer
  tokens. Carry them as `Authorization: Bearer <token>` on subsequent
  requests.

`require_role("admin")` and `require_role("user")` factories are used
internally to gate role-sensitive routes.
