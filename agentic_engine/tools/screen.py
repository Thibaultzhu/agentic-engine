"""Computer Use — screenshot / click / type / move tools.

Uses pyautogui (cross-platform) and mss (fast screenshot). Both are optional;
the tools degrade gracefully with a clear error message if not installed.

Install:  pip install pyautogui mss pillow
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

from ..core.tool import tool


def _require(modname: str):
    try:
        return __import__(modname)
    except ImportError as e:
        raise RuntimeError(
            f"'{modname}' is not installed. Run `pip install pyautogui mss pillow`."
        ) from e


@tool(name="screen_grab", description="Capture screen and save to PNG. Returns saved path.")
def screen_grab(output: str = "screenshot.png", monitor: int = 1) -> str:
    try:
        mss = _require("mss")
        with mss.mss() as sct:
            mons = sct.monitors
            if monitor < 0 or monitor >= len(mons):
                return f"[error] monitor {monitor} out of range (have {len(mons) - 1})"
            img = sct.grab(mons[monitor])
            from mss.tools import to_png
            data = to_png(img.rgb, img.size)
        path = Path(output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


@tool(name="screen_grab_b64", description="Capture screen and return base64 PNG (truncated for safety).")
def screen_grab_b64(monitor: int = 1) -> str:
    try:
        mss = _require("mss")
        with mss.mss() as sct:
            img = sct.grab(sct.monitors[monitor])
            from mss.tools import to_png
            data = to_png(img.rgb, img.size)
        b64 = base64.b64encode(data).decode("ascii")
        return b64[:120000]
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


@tool(name="mouse_click", description="Click at (x,y). button: left|right|middle.",
      requires_approval=True)
def mouse_click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    try:
        pg = _require("pyautogui")
        pg.click(x=x, y=y, button=button, clicks=clicks)
        return f"clicked ({x},{y}) button={button} x{clicks}"
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


@tool(name="mouse_move", description="Move mouse to (x,y).", requires_approval=True)
def mouse_move(x: int, y: int, duration: float = 0.2) -> str:
    try:
        pg = _require("pyautogui")
        pg.moveTo(x, y, duration=duration)
        return f"moved to ({x},{y})"
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


@tool(name="keyboard_type", description="Type a string at the current cursor position.",
      requires_approval=True)
def keyboard_type(text: str, interval: float = 0.02) -> str:
    try:
        pg = _require("pyautogui")
        pg.typewrite(text, interval=interval)
        return f"typed {len(text)} chars"
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


@tool(name="keyboard_hotkey", description="Press a hotkey combo, e.g. 'cmd,c' or 'ctrl,shift,t'.",
      requires_approval=True)
def keyboard_hotkey(keys: str) -> str:
    try:
        pg = _require("pyautogui")
        parts = [k.strip() for k in keys.split(",") if k.strip()]
        pg.hotkey(*parts)
        return f"hotkey {parts}"
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


@tool(name="screen_size", description="Return current screen size (width, height).", read_only=True)
def screen_size() -> str:
    try:
        pg = _require("pyautogui")
        w, h = pg.size()
        return f"{w}x{h}"
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"
