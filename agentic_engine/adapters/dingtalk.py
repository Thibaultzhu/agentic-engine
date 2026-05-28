"""DingTalk adapter — webhook stub."""
from __future__ import annotations

import os
from typing import Callable

import httpx

from .base import IMAdapter, IMMessage


class DingTalkAdapter(IMAdapter):
    name = "dingtalk"

    def __init__(self, webhook: str | None = None):
        self.webhook = webhook or os.getenv("DINGTALK_WEBHOOK", "")

    def send(self, chat_id: str, text: str) -> bool:
        if not self.webhook:
            print(f"[dingtalk stub] would send to {chat_id}: {text[:80]}")
            return False
        try:
            r = httpx.post(
                self.webhook,
                json={"msgtype": "text", "text": {"content": text}},
                timeout=10.0,
            )
            return r.status_code == 200
        except Exception as e:  # noqa: BLE001
            print(f"[dingtalk] send failed: {e}")
            return False

    def listen(self, on_message: Callable[[IMMessage], None]) -> None:
        raise NotImplementedError(
            "DingTalkAdapter.listen requires the open-platform callback server."
        )
