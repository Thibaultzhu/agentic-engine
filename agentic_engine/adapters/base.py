"""IM adapter base class — common contract for all chat-channel integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


@dataclass
class IMMessage:
    channel: str          # platform name: feishu, dingtalk, ...
    chat_id: str          # group / user identifier
    sender: str
    text: str
    raw: dict | None = None


class IMAdapter(ABC):
    """Outbound + inbound contract. Subclasses implement send + receive."""

    name: str = "base"

    @abstractmethod
    def send(self, chat_id: str, text: str) -> bool: ...

    @abstractmethod
    def listen(self, on_message: Callable[[IMMessage], None]) -> None:
        """Block (or run a server) and forward inbound messages to on_message."""
        ...
