"""Equity series, external flows and flow-adjusted returns (plan §5.2-5.4).

Equity comes from `portfolio` perp-only histories; deposits/withdrawals never move the
Modified-Dietz time-weighted return (TWR). Non-trading income (rewards, vault commissions)
is treated as an external flow so it cannot masquerade as trading skill.
"""

from __future__ import annotations

import json
import math

import polars as pl

FLOW_SCHEMA = {"time": pl.Int64, "flow": pl.Float64, "kind": pl.Utf8}
INCOME_TYPES = {"rewardsClaim", "vaultLeaderCommission", "vaultDistribution"}


def _raw(row: dict) -> dict:
    return json.loads(row["raw_json"]) if row.get("raw_json") else {}


def flow_events(ledger: pl.DataFrame, address: str) -> pl.DataFrame:
    """Signed USDC flows into (+) / out of (-) the perp account, from ledger deltas (App. B)."""
    me = address.lower()
    out: list[dict] = []
    for r in ledger.iter_rows(named=True):
        t, ty = r["type"], r["type"]
        usdc = r["usdc"] or 0.0
        user = (r["user"] or "").lower()
        dest = (r["destination"] or "").lower()
        fee = r["fee"] or 0.0
        f = 0.0
        if ty == "deposit":
            f = usdc
        elif ty == "withdraw":
            f = -(usdc + fee)
        elif ty == "accountClassTransfer":
            f = usdc if r["to_perp"] else -usdc
        elif ty in ("internalTransfer", "subAccountTransfer"):
            f = usdc if dest == me and user != me else -(usdc + fee) if user == me else 0.0
        elif ty == "send":
            if (r["token"] or "").upper() == "USDC":
                d = _raw(r)
                amt = r["amount"] or 0.0
                if user == me and d.get("sourceDex", "") == "" and dest != me:
                    f = -(amt + fee)
                elif user == me and dest == me:
                    f = amt if d.get("destinationDex", "") == "" and d.get("sourceDex", "") != "" \
                        else -amt if d.get("sourceDex", "") == "" and d.get("destinationDex", "") != "" \
                        else 0.0
                elif dest == me and d.get("destinationDex", "") == "":
                    f = amt
        elif ty == "vaultDeposit":
            f = -usdc
        elif ty == "vaultWithdraw":
            f = float(_raw(r).get("netWithdrawnUsd") or 0.0)
        elif ty in INCOME_TYPES:
            f = float(_raw(r).get("usdc") or _raw(r).get("commission") or usdc or 0.0)
        if f:
            out.append({"time": r["time"], "flow": f, "kind": t})
        del t
    return pl.DataFrame(out, schema=FLOW_SCHEMA)


def equity_series(portfolio: dict, key: str = "perpAllTime") -> pl.DataFrame:
    p = portfolio[key]
    eq = pl.DataFrame({"time": [int(x[0]) for x in p["accountValueHistory"]],
                       "equity": [float(x[1]) for x in p["accountValueHistory"]]})
    pnl = pl.DataFrame({"time": [int(x[0]) for x in p["pnlHistory"]],
                        "cum_pnl": [float(x[1]) for x in p["pnlHistory"]]})
    return eq.join(pnl, on="time", how="left").sort("time").with_columns(
        pl.col("cum_pnl").forward_fill())


def twr_curve(equity: pl.DataFrame, flows: pl.DataFrame) -> pl.DataFrame:
    """Per-observation-interval Modified-Dietz returns, TWR index and drawdown.

    r = (E1 - E0 - F) / (E0 + sum_i F_i * w_i), w_i = fraction of the interval the flow was present.
    """
    e = equity.sort("time").to_dicts()
    fl = flows.sort("time").to_dicts() if not flows.is_empty() else []
    rows = []
    idx, peak, j = 1.0, 1.0, 0
    for i in range(1, len(e)):
        t0, t1 = e[i - 1]["time"], e[i]["time"]
        E0, E1 = e[i - 1]["equity"], e[i]["equity"]
        F = W = 0.0
        while j < len(fl) and fl[j]["time"] <= t1:
            if fl[j]["time"] > t0:
                F += fl[j]["flow"]
                W += fl[j]["flow"] * (t1 - fl[j]["time"]) / max(1, t1 - t0)
            j += 1
        denom = E0 + W
        # tiny/negative base vs. the flow makes Dietz unstable (coarse points): skip the interval
        stable = denom >= max(50.0, 0.25 * abs(F))
        r = (E1 - E0 - F) / denom if stable else 0.0
        r = max(r, -0.999)
        idx *= 1 + r
        peak = max(peak, idx)
        rows.append({"time": t1, "equity": E1, "flow": F, "r": r, "stable": stable, "twr_index": idx,
                     "dd": 1 - idx / peak, "dt_h": (t1 - t0) / 3.6e6})
    return pl.DataFrame(rows, schema={"time": pl.Int64, "equity": pl.Float64, "flow": pl.Float64,
                                      "r": pl.Float64, "stable": pl.Boolean, "twr_index": pl.Float64, "dd": pl.Float64,
                                      "dt_h": pl.Float64})


def daily_returns(curve: pl.DataFrame) -> pl.DataFrame:
    """Compound interval returns by UTC end-day. Days without an observation are omitted."""
    if curve.is_empty():
        return pl.DataFrame(schema={"date": pl.Date, "r": pl.Float64})
    return (curve.with_columns(pl.from_epoch("time", time_unit="ms").dt.date().alias("date"))
            .group_by("date").agg(((1 + pl.col("r")).product() - 1).alias("r")).sort("date"))


def max_drawdown(curve: pl.DataFrame) -> float:
    return float(curve["dd"].max() or 0.0) if not curve.is_empty() else 0.0


def sharpe(daily: pl.DataFrame, periods: int = 365) -> float:
    r = daily["r"]
    if r.len() < 2 or not (r.std() or 0) > 0:
        return 0.0
    return float(r.mean() / r.std() * math.sqrt(periods))


def reconcile(fills: pl.DataFrame, funding: pl.DataFrame, portfolio: dict,
              start_ms: int | None = None, key: str = "perpAllTime",
              capital: float = 0.0) -> dict:
    """Compare our net trading PnL with the platform's pnlHistory delta over the same window.

    Residual / max(peak equity, gross inflows) must be < 2% or the wallet is `reconcile_fail` (plan §5.4).
    """
    eq = equity_series(portfolio, key)
    if eq.is_empty() or fills.is_empty():
        return {"ok": False, "reason": "no_data", "residual_pct": None}
    start = start_ms if start_ms is not None else int(fills["time"].min())
    start = max(start, int(eq["time"].min()))
    end = int(eq["time"].max())
    pnl_at = lambda t: float(eq.filter(pl.col("time") <= t)["cum_pnl"].last() or 0.0)
    platform = pnl_at(end) - pnl_at(start)
    w = (pl.col("time") > start) & (pl.col("time") <= end)
    ours = (fills.filter(w)["closed_pnl"].sum() - fills.filter(w)["fee"].sum()
            + (funding.filter(w)["usdc"].sum() if not funding.is_empty() else 0.0))
    scale = max(float(eq["equity"].max()), capital, 1.0)  # capital = gross inflows
    resid = (ours - platform) / scale
    return {"ok": abs(resid) < 0.02, "ours": ours, "platform": platform,
            "residual_pct": resid * 100, "residual_of_pnl_pct":
            (ours - platform) / abs(platform) * 100 if abs(platform) > 1 else None,
            "window": (start, end)}
