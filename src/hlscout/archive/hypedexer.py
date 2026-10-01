"""Hypedexer archive source (plan §4.4): fills older than the public API's ~10k-fill window.

Docs: GET {base}/fills/user/{address}?start_time&end_time&limit&cursor, X-API-Key header,
response {data, total_count, next_cursor, has_more}. The key comes from HYPEDEXER_API_KEY and is
never logged. Archive fills may lack startPosition/closedPnl/fee; `derive_closed_pnl` fills the
gap from a running average entry so the round-trip engine can use them.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
import polars as pl

from hlscout.ingest.hydrate import FILL_SCHEMA

BASE = "https://api.hypedexer.com"


class Getter(Protocol):
    async def get(self, url: str, params: dict[str, Any]) -> dict[str, Any]: ...


class HttpGetter:
    def __init__(self, key: str, base: str = BASE) -> None:
        self.base = base
        self.client = httpx.AsyncClient(headers={"X-API-Key": key}, timeout=30)

    async def get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        r = await self.client.get(self.base + url, params=params)
        r.raise_for_status()
        return r.json()


def getter_from_env() -> HttpGetter | None:
    key = os.environ.get("HYPEDEXER_API_KEY")
    return HttpGetter(key) if key else None


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_archive_fill(r: dict[str, Any]) -> dict[str, Any]:
    t = r["time"]
    if isinstance(t, str):
        t = int(datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000)
    side = "B" if str(r["side"]).upper() in ("B", "BUY") else "A"
    liq = r.get("isLiquidation")
    return {
        "time": int(t), "coin": r["coin"], "px": float(r["px"]), "sz": float(r["sz"]), "side": side,
        "dir": r.get("dir", "") or "", "start_position": _opt(r.get("startPosition")),
        "closed_pnl": float(r["closedPnl"]) if r.get("closedPnl") is not None else float("nan"),
        "fee": float(r.get("fee") or 0), "crossed": r.get("crossed"), "oid": r.get("oid"),
        "tid": int(r["tid"]), "twap_id": r.get("twapId"), "fee_token": r.get("feeToken"),
        "liquidation": '{"liquidatedUser":"self"}' if liq else None, "hash": r.get("hash"),
    }


def _opt(x: Any) -> float | None:
    return None if x is None else float(x)


async def fetch_fills(g: Getter, address: str, start_ms: int, end_ms: int, limit: int = 1000,
                      max_rows: int = 500_000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = None
    while len(out) < max_rows:
        params: dict[str, Any] = {"start_time": _iso(start_ms), "end_time": _iso(end_ms), "limit": limit}
        if cursor:
            params["cursor"] = cursor
        page = await g.get(f"/fills/user/{address}", params)
        out.extend(norm_archive_fill(r) for r in page.get("data", []))
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            break
    return out


def derive_closed_pnl(fills: pl.DataFrame) -> pl.DataFrame:
    """Fill NaN closed_pnl and null start_position by replaying per coin with a running average entry."""
    if fills.is_empty():
        return fills
    rows = []
    for _, g in fills.sort(["coin", "time", "tid"]).group_by("coin", maintain_order=True):
        pos = entry = 0.0
        for r in g.to_dicts():
            signed = r["sz"] if r["side"] == "B" else -r["sz"]
            if r["start_position"] is None:
                r["start_position"] = pos
            pnl = 0.0
            if pos * signed < 0:  # reducing or flipping
                closed = min(abs(signed), abs(pos))
                pnl = (r["px"] - entry) * closed * (1 if pos > 0 else -1)
            new = pos + signed
            if pos == 0 or pos * signed > 0:
                entry = (abs(pos) * entry + abs(signed) * r["px"]) / abs(new) if new else 0.0
            elif abs(signed) > abs(pos):
                entry = r["px"]
            pos = 0.0 if abs(new) < 1e-9 else new
            if abs(pos) < 1e-9:
                entry = 0.0
            if r["closed_pnl"] != r["closed_pnl"]:  # NaN
                r["closed_pnl"] = pnl
            rows.append(r)
    return pl.DataFrame(rows, schema=FILL_SCHEMA).sort("time")
