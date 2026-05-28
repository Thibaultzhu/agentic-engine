"""Telegram Bot adapter — uses the official Bot API over HTTPS.

Token comes from @BotFather (env var TELEGRAM_BOT_TOKEN).
Inbound polling uses long-polling getUpdates so no public callback URL needed.
"""
from __future__ import annotations

import os
import time
from typing import Callable

import httpx

from .base import IMAdapter, IMMessage


class TelegramAdapter(IMAdapter):
    name = "telegram"

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._offset: int = 0
        self._stop = False

    def _api(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send(self, chat_id: str, text: str) -> bool:
        if not self.token:
            print(f"[telegram stub] would send to {chat_id}: {text[:80]}")
            return False
        try:
            r = httpx.post(
                self._api("sendMessage"),
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=15,
            )
            return r.status_code == 200
        except Exception as e:
            print(f"[telegram] send failed: {e}")
            return False

    def listen(self, on_message: Callable[[IMMessage], None]) -> None:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
        while not self._stop:
            try:
                r = httpx.get(
                    self._api("getUpdates"),
                    params={"timeout": 30, "offset": self._offset + 1},
                    timeout=40,
                )
                data = r.json()
            except Exception as e:
                print(f"[telegram] poll error: {e}")
                time.sleep(3)
                continue
            for update in data.get("result", []):
                self._offset = max(self._offset, update["update_id"])
                msg = update.get("message") or update.get("channel_post")
                if not msg:
                    continue
                text = msg.get("text") or msg.get("caption") or ""
                im = IMMessage(
                    channel="telegram",
                    chat_id=str(msg["chat"]["id"]),
                    sender=str(msg.get("from", {}).get("username") or msg.get("from", {}).get("id", "")),
                    text=text,
                    raw=update,
                )
                try:
                    on_message(im)
                except Exception as e:
                    print(f"[telegram] handler error: {e}")

    def stop(self) -> None:
        self._stop = True
