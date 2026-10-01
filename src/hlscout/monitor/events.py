"""Watchlist state diffing and re-vet triggers (plan §9). Pure functions, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Snap:
    ts: int
    equity: float
    notional: float
    positions: dict[str, dict[str, float]]  # coin -> {szi, upnl, liq, lev}

    @classmethod
    def from_states(cls, states: list[dict[str, Any]], ts: int) -> Snap:
        """`states` is [{dex, state}] as stored by hydrate_deep (one clearinghouseState per dex)."""
        eq = ntl = 0.0
        pos: dict[str, dict[str, float]] = {}
        for s in states:
            st = s["state"]
            ms = st.get("marginSummary", {})
            eq += float(ms.get("accountValue", 0))
            ntl += float(ms.get("totalNtlPos", 0))
            for p in st.get("assetPositions", []):
                q = p["position"]
                szi = float(q["szi"])
                if szi:
                    liq = q.get("liquidationPx")
                    pos[q["coin"]] = {"szi": szi, "upnl": float(q.get("unrealizedPnl", 0)),
                                      "liq": float(liq) if liq else 0.0,
                                      "lev": float((q.get("leverage") or {}).get("value", 0))}
        return cls(ts, eq, ntl, pos)


@dataclass
class Envelope:
    """Baseline from the backtest: what 'normal' looks like for this wallet."""
    max_leverage: float = 10.0
    max_dd: float = 0.30
    peak_equity: float = 0.0
    lev_gate_notional_mult: float = 1.0


@dataclass
class Event:
    address: str
    ts: int
    event: str
    coin: str | None = None
    notional: float = 0.0
    revet: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


def diff_state(address: str, prev: Snap | None, cur: Snap) -> list[Event]:
    if prev is None:
        return []
    out = []
    for coin in set(prev.positions) | set(cur.positions):
        a, b = prev.positions.get(coin), cur.positions.get(coin)
        pa, pb = (a or {}).get("szi", 0.0), (b or {}).get("szi", 0.0)
        if pa == pb:
            continue
        if not a:
            kind = "open"
        elif not b:
            kind = "close"
        elif pa * pb < 0:
            kind = "flip"
        elif abs(pb) > abs(pa):
            kind = "add"
        else:
            kind = "reduce"
        out.append(Event(address, cur.ts, kind, coin, abs(pb - pa), detail={"from": pa, "to": pb}))
    return out


def check_triggers(address: str, prev: Snap | None, cur: Snap, env: Envelope,
                   inflows: list[tuple[int, float]] | None = None) -> list[Event]:
    """Immediate re-vet triggers: liquidation, leverage breach, DD breach, rescue-pattern inflow."""
    out: list[Event] = []
    if prev is not None:
        for coin, p in prev.positions.items():
            c = cur.positions.get(coin)
            gone = c is None
            # a position that vanished while it was near its liquidation price, with equity cratering
            if gone and p["liq"] and cur.equity < 0.7 * prev.equity and p["upnl"] < 0:
                out.append(Event(address, cur.ts, "liquidation", coin, abs(p["szi"]), True,
                                 {"prev_equity": prev.equity, "equity": cur.equity}))
    if cur.equity > 0:
        lev = cur.notional / cur.equity
        if lev > env.max_leverage:
            out.append(Event(address, cur.ts, "leverage_breach", None, cur.notional, True, {"lev": lev}))
    peak = max(env.peak_equity, cur.equity, prev.equity if prev else 0.0)
    if peak > 0 and not inflows and 1 - cur.equity / peak > env.max_dd:
        out.append(Event(address, cur.ts, "dd_breach", None, 0.0, True, {"dd": 1 - cur.equity / peak}))
    for ts, amt in inflows or []:
        ref = prev or cur
        upnl = sum(p["upnl"] for p in ref.positions.values())
        base = max(ref.equity, 1.0)
        if amt >= 0.15 * base and upnl <= -0.25 * base:
            out.append(Event(address, ts, "rescue_inflow", None, amt, True,
                             {"upnl": upnl, "equity": ref.equity}))
    return out


def flock(events: list[Event], window_ms: int = 15 * 60_000, min_wallets: int = 2) -> list[dict]:
    """>= 2 watched wallets opening/adding the same coin and direction inside the window."""
    opens = sorted((e for e in events if e.event in ("open", "add") and e.coin), key=lambda e: e.ts)
    out, seen = [], set()
    for i, e in enumerate(opens):
        d = 1 if e.detail.get("to", 0) > 0 else -1
        grp = {x.address for x in opens[i:] if x.coin == e.coin and x.ts - e.ts <= window_ms
               and (1 if x.detail.get("to", 0) > 0 else -1) == d}
        key = (e.coin, d, e.ts // window_ms)
        if len(grp) >= min_wallets and key not in seen:
            seen.add(key)
            out.append({"coin": e.coin, "dir": "long" if d > 0 else "short", "wallets": sorted(grp), "ts": e.ts})
    return out
