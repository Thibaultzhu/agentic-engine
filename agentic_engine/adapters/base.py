"""IM adapter base class — common contract for all chat-channel integrations.

The original ``IMAdapter`` lumped outbound and inbound capabilities together,
which meant adapters that can only send (e.g. webhook-only group bots) had to
raise ``NotImplementedError`` from ``listen``. The split below lets each
concrete adapter declare exactly what it supports.

For backwards compatibility ``IMAdapter`` is still exported and inherits
from both protocols.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class IMMessage:
    channel: str          # platform name: feishu, dingtalk, ...
    chat_id: str          # group / user identifier
    sender: str
    text: str
    raw: dict | None = None


class IMSender(ABC):
    """Outbound capability."""

    name: str = "base"

    @abstractmethod
    def send(self, chat_id: str, text: str) -> bool: ...


class IMReceiver(ABC):
    """Inbound capability — blocks and forwards messages."""

    name: str = "base"

    @abstractmethod
    def listen(self, on_message: Callable[[IMMessage], None]) -> None: ...


class IMAdapter(IMSender, IMReceiver):
    """Full bidirectional adapter (kept for backwards compat)."""
