# Desktop shell

The `desktop/` directory contains a [Tauri 2.x](https://v2.tauri.app/)
configuration that ships the FastAPI server inside a native window.

See [`desktop/README.md`](https://github.com/Thibaultzhu/agentic-engine/blob/main/desktop/README.md)
for build / dev / packaging steps. Highlights:

* The Python process is launched as Tauri's `beforeDevCommand`
  (`uvicorn agentic_engine.server:app --port 8765 --reload`).
* The webview navigates to `http://127.0.0.1:8765/h5/page` once the
  port is listening.
* CSP locks fetches/sockets to `http://127.0.0.1:8765` and
  `ws://127.0.0.1:8765` — loopback only.

## Why Tauri rather than Electron?

* **<10 MB bundle** vs. ~150 MB.
* Native webview (WKWebView / WebView2 / WebKitGTK) — no Chromium fork.
* Rust core is sandboxed and small enough to audit.
* Bundle targets cover macOS (`dmg`), Windows (`msi`), Linux (`deb`,
  `appimage`) out of the box.

## Code-signing

For distribution, sign the bundle with the platform-native tool chain:

```bash
# macOS
codesign --deep --force --options runtime \
  --sign "Developer ID Application: ..." \
  desktop/target/release/bundle/macos/Agentic\ Engine.app

# Windows (via signtool with EV cert)
signtool sign /tr http://timestamp.digicert.com /td sha256 \
  /fd sha256 /a desktop\target\release\bundle\msi\*.msi
```

Tauri's signing config can also be wired into
`desktop/tauri.conf.json`'s `bundle.macOS.signingIdentity` for
fully-automated CI builds.
