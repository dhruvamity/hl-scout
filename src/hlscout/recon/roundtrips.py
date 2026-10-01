"""Position replay and round-trip construction (plan §5.1).

HL is one-way per coin per account, so a round trip is flat -> non-zero -> flat on one coin.
A fill that crosses zero is split: the part closing the old position and the part opening
the new one. startPosition is used to check continuity; a jump marks the coin incomplete.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import polars as pl

EPS = 1e-9
CLIP_WINDOW_MS = 2000
TRIP_SCHEMA = {
    "coin": pl.Utf8, "open_ts": pl.Int64, "close_ts": pl.Int64, "side": pl.Utf8,
    "max_size": pl.Float64, "adds": pl.Int64, "reduces": pl.Int64, "vwap_in": pl.Float64,
    "vwap_out": pl.Float64, "pnl": pl.Float64, "fees": pl.Float64, "funding": pl.Float64,
    "liquidated": pl.Boolean, "twap_share": pl.Float64, "underwater_add_share": pl.Float64,
    "first_clip": pl.Float64, "complete": pl.Boolean, "n_fills": pl.Int64,
    "open_notional": pl.Float64, "maker_fills": pl.Int64,
}


@dataclass
class _Trip:
    coin: str
    side: str
    open_ts: int
    entry_px: float = 0.0     # running average entry
    max_size: float = 0.0
    first_clip: float = 0.0
    adds: int = 0
    reduces: int = 0
    in_notional: float = 0.0
    in_size: float = 0.0
    out_notional: float = 0.0
    out_size: float = 0.0
    pnl: float = 0.0
    fees: float = 0.0
    liquidated: bool = False
    twap_vol: float = 0.0
    vol: float = 0.0
    add_notional: float = 0.0
    underwater_add_notional: float = 0.0
    n_fills: int = 0
    maker_fills: int = 0
    open_notional: float = 0.0
    complete: bool = True
    close_ts: int = 0
    open_oid: int | None = None


def perp_only(fills: pl.DataFrame) -> pl.DataFrame:
    """Drop spot fills (`@n` indices and `BASE/QUOTE` pairs); HIP-3 perps (`dex:COIN`) stay."""
    return fills.filter(~pl.col("coin").str.starts_with("@") & ~pl.col("coin").str.contains("/"))


def _is_liq(d: str, liq: str | None, address: str | None = None) -> bool:
    """True if this fill closed *our* position by liquidation (not us acting as liquidator)."""
    if "liquidat" in (d or "").lower():
        return True
    if not liq:
        return False
    victim = (json.loads(liq).get("liquidatedUser") or "").lower()
    return not victim or address is None or victim == address.lower()


def _chain_order(rows: list[dict]) -> list[dict]:
    """Order same-millisecond fills by following startPosition -> startPosition + signed size."""
    if len(rows) < 2 or any(r["start_position"] is None for r in rows):
        return rows

    def key(x: float) -> float:
        return round(x, 6)

    ends = {key(r["start_position"] + (r["sz"] if r["side"] == "B" else -r["sz"])) for r in rows}
    starts = [r for r in rows if key(r["start_position"]) not in ends]
    by_start: dict[float, list[dict]] = {}
    for r in rows:
        by_start.setdefault(key(r["start_position"]), []).append(r)
    cur = starts[0] if starts else rows[0]
    out = []
    used = set()
    while cur is not None and id(cur) not in used:
        out.append(cur)
        used.add(id(cur))
        nxt = key(cur["start_position"] + (cur["sz"] if cur["side"] == "B" else -cur["sz"]))
        cur = next((c for c in by_start.get(nxt, []) if id(c) not in used), None)
    return out if len(out) == len(rows) else rows


def _ordered_rows(g: pl.DataFrame) -> list[dict]:
    rows = g.sort(["time", "tid"]).to_dicts()
    out: list[dict] = []
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j]["time"] == rows[i]["time"]:
            j += 1
        out.extend(_chain_order(rows[i:j]))
        i = j
    return out


def build_round_trips(
    fills: pl.DataFrame, funding: pl.DataFrame | None = None, address: str | None = None
) -> tuple[pl.DataFrame, set[str]]:
    """Returns (closed round trips, coins with continuity breaks)."""
    broken: set[str] = set()
    trips: list[dict] = []
    if fills.is_empty():
        return pl.DataFrame(schema=TRIP_SCHEMA), broken
    f = fills.sort(["coin", "time", "tid"])
    for key, g in f.group_by("coin", maintain_order=True):
        coin = key[0]
        pos = 0.0
        trip: _Trip | None = None
        for r in _ordered_rows(g):
            signed = r["sz"] if r["side"] == "B" else -r["sz"]
            sp = r["start_position"]
            if sp is not None and abs(sp - pos) > max(1e-6, 1e-6 * abs(sp)):
                broken.add(coin)  # missing fills: resync to the exchange's view
                if trip is not None:
                    trip.complete = False
                if abs(sp) < EPS:
                    trip, pos = None, 0.0
                else:
                    pos = sp
                    if trip is None:  # unknown history before this point
                        trip = _Trip(coin, "long" if sp > 0 else "short", r["time"],
                                     entry_px=r["px"], complete=False)
                        trip.max_size = abs(sp)
            fee, pnl = r["fee"], r["closed_pnl"]
            liq = _is_liq(r["dir"], r["liquidation"], address)
            remaining = signed
            first = True
            while abs(remaining) > EPS:
                if abs(pos) < EPS:  # flat -> open
                    trip = _Trip(coin, "long" if remaining > 0 else "short", r["time"],
                                 complete=coin not in broken)
                    pos = 0.0
                same_dir = pos * remaining >= 0
                qty = remaining if same_dir else (-pos if abs(remaining) > abs(pos) else remaining)
                new_pos = pos + qty
                frac = abs(qty) / abs(signed)
                if first:
                    trip.n_fills += 1
                    if r["crossed"] is False:
                        trip.maker_fills += 1
                trip.fees += fee * frac
                trip.pnl += pnl * frac
                trip.vol += abs(qty)
                if r["twap_id"] is not None:
                    trip.twap_vol += abs(qty)
                trip.liquidated |= liq
                if same_dir:
                    if abs(pos) < EPS:
                        trip.first_clip = abs(qty)
                        trip.open_notional = abs(qty) * r["px"]
                        trip.open_oid = r["oid"]
                    elif (r["oid"] is not None and r["oid"] == trip.open_oid) or \
                            (trip.adds == 0 and r["time"] - trip.open_ts <= CLIP_WINDOW_MS):
                        # partial fills of the opening order (or a burst within 2 s) are one clip,
                        # not scale-ins: otherwise a tiny first partial fill inflates "multiple"
                        trip.first_clip += abs(qty)
                        trip.open_notional += abs(qty) * r["px"]
                    else:
                        trip.adds += 1
                        trip.add_notional += abs(qty) * r["px"]
                        worse = r["px"] < trip.entry_px if qty > 0 else r["px"] > trip.entry_px
                        if worse:
                            trip.underwater_add_notional += abs(qty) * r["px"]
                    trip.entry_px = (abs(pos) * trip.entry_px + abs(qty) * r["px"]) / abs(new_pos)
                    trip.in_notional += abs(qty) * r["px"]
                    trip.in_size += abs(qty)
                else:
                    trip.reduces += 1
                    trip.out_notional += abs(qty) * r["px"]
                    trip.out_size += abs(qty)
                pos = new_pos
                trip.max_size = max(trip.max_size, abs(pos))
                remaining -= qty
                first = False
                if abs(pos) < EPS:
                    trip.close_ts = r["time"]
                    trips.append(_finish(trip))
                    trip, pos = None, 0.0
        # an unclosed trip is the live position, not a round trip
    df = pl.DataFrame(trips, schema=TRIP_SCHEMA).sort("open_ts")
    if funding is not None and not funding.is_empty() and not df.is_empty():
        df = _allocate_funding(df, funding)
    return df, broken


def _finish(t: _Trip) -> dict:
    return {
        "coin": t.coin, "open_ts": t.open_ts, "close_ts": t.close_ts, "side": t.side,
        "max_size": t.max_size, "adds": t.adds, "reduces": t.reduces,
        "vwap_in": t.in_notional / t.in_size if t.in_size else 0.0,
        "vwap_out": t.out_notional / t.out_size if t.out_size else 0.0,
        "pnl": t.pnl, "fees": t.fees, "funding": 0.0, "liquidated": t.liquidated,
        "twap_share": t.twap_vol / t.vol if t.vol else 0.0,
        "underwater_add_share": t.underwater_add_notional / t.add_notional
        if t.add_notional else 0.0,
        "first_clip": t.first_clip, "complete": t.complete, "n_fills": t.n_fills,
        "open_notional": t.open_notional, "maker_fills": t.maker_fills,
    }


def _allocate_funding(trips: pl.DataFrame, funding: pl.DataFrame) -> pl.DataFrame:
    """Sum funding payments per coin falling inside each trip's [open, close] window."""
    by_coin = {k[0]: g for k, g in funding.group_by("coin")}
    out = []
    for r in trips.iter_rows(named=True):
        g = by_coin.get(r["coin"])
        out.append(0.0 if g is None else g.filter(
            (pl.col("time") >= r["open_ts"]) & (pl.col("time") <= r["close_ts"]))["usdc"].sum())
    return trips.with_columns(pl.Series("funding", out, dtype=pl.Float64))
