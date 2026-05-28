"""Telegram Bot adapter — uses the official Bot API over HTTPS.

Token comes from @BotFather (env var TELEGRAM_BOT_TOKEN).
Inbound polling uses long-polling getUpdates so no public callback URL needed.

Robustness:
    - Exponential backoff on transient errors (network/5xx).
    - Fatal HTTP statuses (401 invalid token, 403 bot kicked, 404 wrong path)
      escalate by raising — caller decides whether to crash the process.
    - Honours Telegram 429 retry_after when the API rate-limits us.
    - Bounded reconnect attempts (configurable; -1 = forever).
"""
from __future__ import annotations

import logging
import os
import random
import time
from collections.abc import Callable

import httpx

from .base import IMAdapter, IMMessage

logger = logging.getLogger(__name__)


class TelegramFatalError(RuntimeError):
    """Non-recoverable Telegram condition (bad token, bot kicked, etc.)."""


_FATAL_STATUSES = {401, 403, 404}


class TelegramAdapter(IMAdapter):
    name = "telegram"

    def __init__(
        self,
        token: str | None = None,
        max_consecutive_failures: int = 10,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._offset: int = 0
        self._stop = False
        self.max_consecutive_failures = max_consecutive_failures
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff

    def _api(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    # ---------- send ----------
    def send(self, chat_id: str, text: str) -> bool:
        if not self.token:
            logger.warning("[telegram stub] would send to %s: %s", chat_id, text[:80])
            return False
        try:
            r = httpx.post(
                self._api("sendMessage"),
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=15,
            )
            if r.status_code in _FATAL_STATUSES:
                raise TelegramFatalError(f"send fatal status {r.status_code}: {r.text[:200]}")
            return r.status_code == 200
        except TelegramFatalError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("[telegram] send failed: %s", e)
            return False

    # ---------- receive ----------
    def listen(self, on_message: Callable[[IMMessage], None]) -> None:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
        consecutive_failures = 0
        while not self._stop:
            try:
                r = httpx.get(
                    self._api("getUpdates"),
                    params={"timeout": 30, "offset": self._offset + 1},
                    timeout=40,
                )
            except (httpx.TransportError, httpx.TimeoutException) as e:
                consecutive_failures += 1
                if (self.max_consecutive_failures >= 0
                        and consecutive_failures > self.max_consecutive_failures):
                    raise TelegramFatalError(
                        f"network failed {consecutive_failures} times in a row: {e}"
                    ) from e
                self._sleep_backoff(consecutive_failures, reason=f"network: {e}")
                continue

            # Fatal: bad token / bot kicked / wrong path — never recoverable
            if r.status_code in _FATAL_STATUSES:
                raise TelegramFatalError(
                    f"Telegram returned {r.status_code} (likely bad token / kicked); "
                    f"body={r.text[:200]}"
                )

            # Rate-limited — respect server hint
            if r.status_code == 429:
                try:
                    retry = int(r.json().get("parameters", {}).get("retry_after", 5))
                except Exception:
                    retry = 5
                logger.warning("[telegram] rate limited; sleeping %ds", retry)
                time.sleep(retry)
                continue

            # Other transient (5xx etc.)
            if r.status_code >= 500:
                consecutive_failures += 1
                if (self.max_consecutive_failures >= 0
                        and consecutive_failures > self.max_consecutive_failures):
                    raise TelegramFatalError(
                        f"server failed {consecutive_failures} times: {r.status_code}"
                    )
                self._sleep_backoff(consecutive_failures, reason=f"http {r.status_code}")
                continue

            # OK
            consecutive_failures = 0
            try:
                data = r.json()
            except Exception as e:  # noqa: BLE001
                logger.warning("[telegram] bad JSON: %s", e)
                self._sleep_backoff(1, reason="bad json")
                continue
            if not data.get("ok", False):
                logger.warning("[telegram] api not ok: %s", data)
                self._sleep_backoff(1, reason="api not ok")
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
                except Exception as e:  # noqa: BLE001
                    logger.exception("[telegram] handler error: %s", e)

    def stop(self) -> None:
        self._stop = True

    def _sleep_backoff(self, attempt: int, *, reason: str) -> None:
        delay = min(self.max_backoff, self.base_backoff * (2 ** (attempt - 1)))
        delay = delay * (0.5 + random.random())  # full jitter
        logger.warning("[telegram] backoff %.1fs (attempt %d, reason=%s)", delay, attempt, reason)
        # interruptible sleep
        end = time.time() + delay
        while time.time() < end and not self._stop:
            time.sleep(min(0.5, end - time.time()))
