"""Feishu (Lark) adapter — webhook stub.

This is a minimal placeholder. Production users should swap in lark-oapi
or the official open-platform SDK. We only show the contract here.
"""
from __future__ import annotations

import os
from collections.abc import Callable

import httpx

from .base import IMAdapter, IMMessage


class FeishuAdapter(IMAdapter):
    name = "feishu"

    def __init__(self, webhook: str | None = None):
        self.webhook = webhook or os.getenv("FEISHU_WEBHOOK", "")

    def send(self, chat_id: str, text: str) -> bool:
        if not self.webhook:
            print(f"[feishu stub] would send to {chat_id}: {text[:80]}")
            return False
        try:
            r = httpx.post(
                self.webhook,
                json={"msg_type": "text", "content": {"text": text}},
                timeout=10.0,
            )
            return r.status_code == 200
        except Exception as e:  # noqa: BLE001
            print(f"[feishu] send failed: {e}")
            return False

    def listen(self, on_message: Callable[[IMMessage], None]) -> None:
        # Real implementation would run a FastAPI route receiving event subscription
        # callbacks from open.feishu.cn. Stub: do nothing.
        raise NotImplementedError(
            "FeishuAdapter.listen requires the official event-subscription server. "
            "See docs/architecture.md for the integration sketch."
        )
