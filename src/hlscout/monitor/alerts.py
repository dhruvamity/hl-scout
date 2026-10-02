"""Alert sinks: local JSONL log + optional Telegram (send-only; token/chat id from the environment)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, root: Path, sender=None) -> None:
        self.path = Path(root) / "alerts.jsonl"
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat = os.environ.get("TELEGRAM_CHAT_ID")
        self.sender = sender or self._telegram

    async def _telegram(self, text: str) -> None:
        if not (self.token and self.chat):
            return
        async with httpx.AsyncClient(timeout=10) as c:  # sendMessage only: the bot never takes commands
            r = await c.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                             json={"chat_id": self.chat, "text": text})
            if r.status_code >= 400:
                log.warning("telegram send failed: HTTP %s", r.status_code)  # never log the token/url

    async def send(self, kind: str, text: str, **extra) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "kind": kind, "text": text, **extra}) + "\n")
        try:
            await self.sender(f"[{kind}] {text}")
        except Exception as e:
            log.warning("alert delivery failed: %s", type(e).__name__)
