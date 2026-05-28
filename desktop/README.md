# Desktop shell (Tauri 2.x)

A thin, optional native wrapper that hosts the FastAPI server's
`/h5/page` route inside a system webview. The Python process is
launched as a sidecar at startup; the window navigates to
`http://127.0.0.1:8765/h5/page` once the server is listening.

## Prerequisites

```bash
# Rust + Cargo
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Tauri CLI
cargo install create-tauri-app --locked
cargo install tauri-cli --locked --version "^2"
```

## Local dev

```bash
cd desktop
cargo tauri dev
```

`beforeDevCommand` will spawn `uvicorn agentic_engine.server:app --port 8765 --reload`.

## Build native bundle

```bash
cargo tauri build
# artifacts -> desktop/target/release/bundle/{dmg,msi,deb,appimage}/
```

## Configuration knobs

| Env / file                        | Effect                                         |
|-----------------------------------|------------------------------------------------|
| `AGENTIC_ADMIN_KEY`               | Forces admin-key auth (recommended in release) |
| `AGENTIC_JWT_SECRET`              | Enables `/auth/token` issuance + Bearer auth   |
| `AGENTIC_HOME`                    | Override data dir (default `~/.agentic-engine`)|
| `tauri.conf.json` → `app.windows` | Window size, title, default URL                |

## Security notes

* The webview CSP only allows `http://127.0.0.1:8765` and `ws://127.0.0.1:8765` —
  loopback only.
* The FastAPI server inherits the rate-limit middleware (`slowapi`) and the
  same auth surface as headless deployments. There is no extra "trust the
  shell" code path.
* For distribution, code-sign the bundle (macOS `codesign` / Windows
  Authenticode) and ship a hardened runtime — Tauri's defaults are sane.
