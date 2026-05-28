"""WeChat Work (企业微信) group bot adapter — webhook only.

Receives no inbound (group bot is one-way); listen() raises NotImplementedError.
Use the official WeChat Work Open Platform SDK if you need bidirectional.
"""
from __future__ import annotations

import os
from typing import Callable

import httpx

from .base import IMAdapter, IMMessage


class WeChatAdapter(IMAdapter):
    name = "wechat"

    def __init__(self, webhook: str | None = None):
        self.webhook = webhook or os.getenv("WECHAT_WORK_WEBHOOK", "")

    def send(self, chat_id: str, text: str) -> bool:
        if not self.webhook:
            print(f"[wechat stub] would send to {chat_id}: {text[:80]}")
            return False
        try:
            r = httpx.post(
                self.webhook,
                json={"msgtype": "text", "text": {"content": text}},
                timeout=10,
            )
            return r.status_code == 200
        except Exception as e:
            print(f"[wechat] send failed: {e}")
            return False

    def listen(self, on_message: Callable[[IMMessage], None]) -> None:
        raise NotImplementedError(
            "WeChat group bot is one-way. For inbound, use the WeChat Work "
            "Open Platform callback (XML over HTTPS) and wire it to a FastAPI route."
        )
