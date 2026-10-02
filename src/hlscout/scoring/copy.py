"""Copyability card (plan §8.2 optional extra): can a human actually follow this trader?

All figures come from the wallet's round trips. Cost assumptions are configurable defaults, stated in the card:
  taker fee 4.5 bps per side, slippage 2 bps per side -> round-trip cost 13 bps.
"""

from __future__ import annotations

import polars as pl

from hlscout.detectors.base import Ctx

TAKER_BPS, SLIP_BPS = 4.5, 2.0
HYPERLIQUID_MIN_ORDER_USD = 10.0


def copy_card(ctx: Ctx, m: dict) -> dict:
    t = ctx.trips
    if t.is_empty():
        return {}
    recent = t.filter(pl.col("open_ts") >= ctx.now_ms - 180 * 86_400_000)
    t = recent if recent.height >= 20 else t
    notional = t["open_notional"].filter(t["open_notional"] > 0)
    if notional.is_empty():
        return {}
    days = max(1.0, (int(t["close_ts"].max()) - int(t["open_ts"].min())) / 86_400_000)
    lev = None
    if ctx.daily is not None and not ctx.daily.is_empty():
        d = ctx.daily.filter(pl.col("lev") > 0)["lev"]
        lev = float(d.median()) if d.len() else None
    med_notional = float(notional.median())
    cost_bps = 2 * (TAKER_BPS + SLIP_BPS)
    exp_bps = m.get("expectancy_bps")
    margin_per_trade = med_notional / max(lev or 1.0, 1.0)
    return {
        "median_trade_notional": med_notional,
        "p90_trade_notional": float(notional.quantile(0.9)),
        "trades_per_week": t.height / days * 7,
        "median_hold_s": float(((t["close_ts"] - t["open_ts"]) / 1000).median()),
        "median_daily_leverage": lev,
        # one typical position's margin with a 2x buffer; never below Hyperliquid's $10 minimum order
        "min_copy_capital": max(HYPERLIQUID_MIN_ORDER_USD, 2 * margin_per_trade),
        "round_trip_cost_bps": cost_bps,
        "expectancy_bps": exp_bps,
        "edge_after_costs_bps": (exp_bps - cost_bps) if exp_bps is not None else None,
        "copyable": exp_bps is not None and exp_bps > cost_bps,
    }
