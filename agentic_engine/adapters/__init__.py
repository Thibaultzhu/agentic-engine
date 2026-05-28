"""IM channel adapters — abstract base + minimal stubs."""
from .base import IMAdapter, IMMessage
from .feishu import FeishuAdapter
from .dingtalk import DingTalkAdapter
from .telegram import TelegramAdapter
from .wechat import WeChatAdapter

__all__ = [
    "IMAdapter",
    "IMMessage",
    "FeishuAdapter",
    "DingTalkAdapter",
    "TelegramAdapter",
    "WeChatAdapter",
]
