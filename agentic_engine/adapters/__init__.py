"""IM channel adapters — abstract base + minimal stubs."""
from .base import IMAdapter, IMMessage, IMReceiver, IMSender
from .dingtalk import DingTalkAdapter
from .feishu import FeishuAdapter
from .telegram import TelegramAdapter
from .wechat import WeChatAdapter

__all__ = [
    "IMAdapter",
    "IMSender",
    "IMReceiver",
    "IMMessage",
    "FeishuAdapter",
    "DingTalkAdapter",
    "TelegramAdapter",
    "WeChatAdapter",
]
