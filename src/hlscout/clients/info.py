"""Read-only Info API client. Only POSTs to /info; there is deliberately no exchange code."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from hlscout.clients.ratelimit import RateLimiter

log = logging.getLogger(__name__)

# (base weight, rows per +1 surcharge). Re-verify against live docs (scripts/check_docs.py).
BASE_WEIGHT: dict[str, int] = {
    "clearinghouseState": 2,
    "spotClearinghouseState": 2,
    "allMids": 2,
    "l2Book": 2,
    "userRole": 60,
}
DEFAULT_WEIGHT = 20
ROW_SURCHARGE_TYPES = {
    "userFills", "userFillsByTime", "userFunding", "userNonFundingLedgerUpdates",
    "historicalOrders", "fundingHistory", "recentTrades", "candleSnapshot",
    "userTwapSliceFillsByTime", "userTwapSliceFills", "twapHistory",
}
ROWS_PER_WEIGHT = 20
ROWS_PER_WEIGHT_BY_TYPE = {"candleSnapshot": 60}  # rate-limit docs: +1 weight per 60 candles
ALLOWED_HOSTS = {"api.hyperliquid.xyz"}
EXPLORER_URL = "https://rpc.hyperliquid.xyz/explorer"
EXPLORER_WEIGHT = 40


class InfoClient:
    def __init__(
        self,
        limiter: RateLimiter,
        url: str = "https://api.hyperliquid.xyz/info",
        client: httpx.AsyncClient | None = None,
        max_retries: int = 6,
        usage: Any = None,
    ) -> None:
        host = httpx.URL(url).host
        if host not in ALLOWED_HOSTS and host not in ("localhost", "127.0.0.1"):
            raise ValueError(f"host not allowlisted: {host}")
        self.url = url
        self.limiter = limiter
        self._client = client or httpx.AsyncClient(timeout=60)
        self.max_retries = max_retries
        self.usage = usage  # optional (lane, weight) callback for the live tracker

    async def post(self, payload: dict[str, Any], lane: str = "deep_vet") -> Any:
        rtype = payload["type"]
        weight = BASE_WEIGHT.get(rtype, DEFAULT_WEIGHT)
        for _ in range(self.max_retries):
            await self.limiter.acquire(weight, lane)
            if self.usage:
                self.usage(lane, weight)
            resp = await self._client.post(self.url, json=payload)
            if resp.status_code == 429:
                pause = self.limiter.on_429()
                log.warning("429 on %s; pausing %.1fs", rtype, pause)
                continue
            resp.raise_for_status()
            self.limiter.on_success()
            data = resp.json()
            if rtype in ROW_SURCHARGE_TYPES and isinstance(data, list):
                extra = len(data) // ROWS_PER_WEIGHT_BY_TYPE.get(rtype, ROWS_PER_WEIGHT)
                self.limiter.debit(extra)
                if self.usage and extra:
                    self.usage(lane, extra)
            return data
        raise RuntimeError(f"gave up on {rtype} after repeated 429s")

    async def explorer_user_details(self, address: str, lane: str = "deep_vet") -> list[dict[str, Any]]:
        """Recent L1 action log for a user (updateIsolatedMargin, updateLeverage, orders...). Read-only."""
        for _ in range(self.max_retries):
            await self.limiter.acquire(EXPLORER_WEIGHT, lane)
            if self.usage:
                self.usage(lane, EXPLORER_WEIGHT)
            resp = await self._client.post(EXPLORER_URL, json={"type": "userDetails", "user": address})
            if resp.status_code == 429:
                self.limiter.on_429()
                continue
            resp.raise_for_status()
            self.limiter.on_success()
            return resp.json().get("txs", [])
        raise RuntimeError("gave up on explorer userDetails after repeated 429s")

    async def aclose(self) -> None:
        await self._client.aclose()
