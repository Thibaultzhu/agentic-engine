# desktop/

A minimal cross-platform UI shell for `agentic-engine`.

The Python backend (`agentic_engine.server:app`) exposes everything we need
over HTTP. The desktop UI is therefore a thin client.

## Modes

### 1. Web (zero-install, recommended for now)

```bash
# terminal A — start the API
agentic serve --port 9120

# terminal B — open the static client
open desktop/web/index.html
# or serve it:  python -m http.server 8000 --directory desktop/web
```

The web UI lives in `desktop/web/index.html` and talks to `localhost:9120`.

### 2. Tauri wrapper (optional, native window)

The web UI is already self-contained — to wrap it as a desktop app:

```bash
# prerequisites: Rust toolchain + Node 20+
npx create-tauri-app@latest agentic-shell -- --template vanilla --manager npm
# replace src/index.html with desktop/web/index.html
# in tauri.conf.json, set
#   build.devUrl  = "http://localhost:9120"   (optional)
#   build.beforeDevCommand = ""               (we serve from Python)
#   bundle.identifier = "com.agentic.engine"
npm run tauri dev
```

We deliberately do NOT vendor the Tauri sidecar — the FastAPI backend is the
single source of truth. The native shell only renders HTML and forwards
HTTP requests.

## Why no React/Vite?

A single static HTML file (~6 KB) keeps install friction at zero and avoids
build pipelines. If you outgrow it, swap in any framework you like.
