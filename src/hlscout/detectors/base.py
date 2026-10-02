"""Detector plumbing: Finding, context and the shared analysis bundle (plan §6)."""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from hlscout.config import Config
from hlscout.recon import equity as eq
from hlscout.recon.daily import build_daily
from hlscout.recon.positions import Timeline, build_timeline
from hlscout.recon.roundtrips import build_round_trips

DAY_MS = 86_400_000


@dataclass
class Finding:
    code: str
    severity: str  # VETO | FLAG | INFO
    family: str    # M, H, R, C, B
    penalty: float = 0.0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class Ctx:
    address: str
    cfg: Config
    now_ms: int
    fills: pl.DataFrame
    funding: pl.DataFrame
    ledger: pl.DataFrame
    portfolio: dict
    trips: pl.DataFrame
    broken_coins: set[str]
    flows: pl.DataFrame
    equity: pl.DataFrame
    curve: pl.DataFrame
    timeline: Timeline
    states: list[dict]
    role: dict | None = None
    lb: dict | None = None
    marks: Callable[[str, int], float | None] | None = None
    rate_limit: dict | None = None
    coarse_ok: bool = False
    actions: list | None = None
    daily: pl.DataFrame | None = None
    marks_eod: Callable[[str, int], float | None] | None = None
    asset_names: list | None = None
    extra_agents: list | None = None
    _eq_t: list[int] = field(default_factory=list)
    _eq_v: list[float] = field(default_factory=list)

    def equity_at(self, t: int) -> float | None:
        """Last portfolio equity observation at or before t (None if before the first)."""
        i = bisect.bisect_right(self._eq_t, t) - 1
        return self._eq_v[i] if i >= 0 else None

    def window_start(self, days: int) -> int:
        return self.now_ms - days * DAY_MS


def build_ctx(address: str, fills: pl.DataFrame, funding: pl.DataFrame, ledger: pl.DataFrame,
              portfolio: dict, cfg: Config | None = None, now_ms: int | None = None,
              states: list[dict] | None = None, **kw: Any) -> Ctx:
    import time as _t

    cfg = cfg or Config()
    trips, broken = build_round_trips(fills, funding, address)
    flows = eq.flow_events(ledger, address)
    equity = eq.equity_series(portfolio)
    timeline = build_timeline(fills)
    now = now_ms or int(_t.time() * 1000)
    # audit C1: a DAILY curve rebuilt from fills + marks replaces the 1-2-week platform sampling
    daily = build_daily(fills, funding, flows, portfolio, timeline, kw.get("marks_eod"), now)
    curve = daily if not daily.is_empty() else eq.twr_curve(equity, flows)
    ctx = Ctx(
        address=address.lower(), cfg=cfg, now_ms=now, fills=fills,
        funding=funding, ledger=ledger, portfolio=portfolio, trips=trips, broken_coins=broken,
        flows=flows, equity=equity, curve=curve, daily=daily,
        timeline=timeline, states=states or [], **kw)
    # equity_at(): platform points before the first fill day, our daily equity from then on
    first_day = int(daily["time"][0]) - DAY_MS + 1 if not daily.is_empty() else None
    pre = equity.filter(pl.col("time") < first_day) if first_day is not None else equity
    ctx._eq_t = pre["time"].to_list() + (daily["time"].to_list() if first_day is not None else [])
    ctx._eq_v = pre["equity"].to_list() + (daily["equity"].to_list() if first_day is not None else [])
    return ctx
