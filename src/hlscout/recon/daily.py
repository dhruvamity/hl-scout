"""Daily equity engine (audit C1): rebuild the equity/return curve at DAILY resolution from our own data.

The platform's all-time `portfolio` history has one point every 1-2 weeks, which hides drawdowns and
makes Sharpe/t-stat/DSR meaningless. Per UTC day:

    pnl_d  = realised closedPnl - fees + funding + (U_d - U_{d-1})        U = open-position PnL at the day's mark
    E_d    = E_{d-1} + pnl_d + flows_d                                    re-anchored to every platform point
    r_d    = pnl_d / max(E_{d-1} + w*flows_d, floor * peak equity)        Modified-Dietz style

Re-anchoring keeps the curve tied to platform truth; the per-day residual is kept so the audit can see it.
"""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from hlscout.recon.positions import Timeline

DAY_MS = 86_400_000
EOD_WINDOW_MS = 3 * 3_600_000   # anchors this close to day end are treated as end-of-day equity
SOFT_TOL = 0.5                  # a mid-day anchor must differ by > 50% of equity (and 15% of gross) to override us
DAILY_SCHEMA = {
    "time": pl.Int64, "equity": pl.Float64, "flow": pl.Float64, "pnl": pl.Float64, "r": pl.Float64,
    "stable": pl.Boolean, "twr_index": pl.Float64, "dd": pl.Float64, "dt_h": pl.Float64,
    "gross": pl.Float64, "lev": pl.Float64, "resid": pl.Float64, "marked": pl.Boolean,
    "eod_anchor": pl.Boolean,
}


def platform_anchors(portfolio: dict) -> list[tuple[int, float]]:
    """(time, accountValue) from every perp window, finest resolution winning where windows overlap."""
    pts: dict[int, float] = {}
    for key in ("perpAllTime", "perpMonth", "perpWeek", "perpDay"):  # later keys are finer: overwrite
        for t, v in portfolio.get(key, {}).get("accountValueHistory", []) or []:
            pts[int(t)] = float(v)
    return sorted(pts.items())


def _unrealised(tl: Timeline, t_end: int, mark: Callable[[str, int], float | None] | None
                ) -> tuple[float, float, bool]:
    """(open uPnL, gross notional, any position valued at stale last-fill price) at t_end."""
    upnl = gross = 0.0
    fallback = False
    for coin, (pos, entry, last_px, _) in tl.open_positions(t_end).items():
        m = mark(coin, t_end) if mark else None
        if m is None:
            m, fallback = last_px, True
        if m is None:
            continue
        upnl += pos * (m - entry)
        gross += abs(pos) * m
    return upnl, gross, fallback


def build_daily(fills: pl.DataFrame, funding: pl.DataFrame, flows: pl.DataFrame, portfolio: dict,
                timeline: Timeline, mark: Callable[[str, int], float | None] | None, now_ms: int,
                capital_floor: float = 0.5) -> pl.DataFrame:
    if fills.is_empty():
        return pl.DataFrame(schema=DAILY_SCHEMA)
    d0 = int(fills["time"].min()) // DAY_MS
    d1 = now_ms // DAY_MS
    by_day = lambda df, col: dict(
        df.group_by((pl.col("time") // DAY_MS).alias("d")).agg(pl.col(col).sum()).iter_rows()
    ) if not df.is_empty() else {}
    realised = by_day(fills.with_columns((pl.col("closed_pnl") - pl.col("fee")).alias("x")), "x")
    fund = by_day(funding, "usdc") if not funding.is_empty() else {}
    flow = by_day(flows, "flow") if not flows.is_empty() else {}
    anchors = platform_anchors(portfolio)
    ai = 0
    # starting equity: last anchor at or before the first fill day, else the first anchor after it
    e_prev = 0.0
    for t, v in anchors:
        if t <= d0 * DAY_MS:
            e_prev = v
    if not e_prev and anchors:
        e_prev = anchors[0][1]
    u_prev = 0.0
    idx, peak, peak_e = 1.0, 1.0, max(e_prev, 0.0)
    rows = []
    for d in range(d0, d1 + 1):
        t_end = (d + 1) * DAY_MS - 1
        u, gross, stale = _unrealised(timeline, t_end, mark)
        pnl = realised.get(d, 0.0) + fund.get(d, 0.0) + (u - u_prev)
        f = flow.get(d, 0.0)
        e_new = e_prev + pnl + f
        resid = 0.0
        eod_hit = False
        in_day: list[tuple[int, float]] = []
        while ai < len(anchors) and anchors[ai][0] <= t_end:
            if anchors[ai][0] >= d * DAY_MS:
                in_day.append(anchors[ai])
            ai += 1
        if in_day:
            near_eod = [a for a in in_day if a[0] >= t_end - EOD_WINDOW_MS]
            if near_eod:  # an anchor within a few hours of day end: exact enough to adopt
                resid = e_new - near_eod[-1][1]
                e_new = near_eod[-1][1]
                eod_hit = True
            else:
                # an anchor at some other time of day compares against OUR end-of-day value, so for a leveraged
                # wallet most of the gap is intraday price movement, not error. Adopt it only when the gap is too
                # large for timing to explain (a missed flow / unified-margin collateral move).
                tm, av = in_day[-1]
                resid = e_new - av
                if abs(resid) > max(SOFT_TOL * max(abs(av), 1000.0), 0.15 * gross):
                    e_new = av
        denom = max(e_prev + 0.5 * f, capital_floor * peak_e)
        stable = denom >= max(50.0, 0.25 * abs(f), 0.02 * peak_e)
        r = max(pnl / denom, -0.999) if stable else 0.0
        idx *= 1 + r
        peak = max(peak, idx)
        peak_e = max(peak_e, e_new)
        rows.append({"time": t_end, "equity": e_new, "flow": f, "pnl": pnl, "r": r, "stable": stable,
                     "twr_index": idx, "dd": 1 - idx / peak, "dt_h": 24.0, "gross": gross,
                     "lev": gross / e_prev if e_prev > 100 else 0.0, "resid": resid, "marked": not stale,
                     "eod_anchor": eod_hit})
        e_prev, u_prev = e_new, u
    return pl.DataFrame(rows, schema=DAILY_SCHEMA)


def equity_noise(daily: pl.DataFrame, min_days: int = 10) -> float | None:
    """Median |our end-of-day equity - platform equity| / equity over days with an end-of-day platform point.

    Our PnL is validated by the reconcile gate, so a large value means the platform's account value moves for reasons
    the ledger does not explain (collateral moved between spot and perp, other dexes...). The capital base is then
    unreliable and TWR/drawdown/Sharpe are too. Only measurable where the platform publishes day-end points
    (the last ~30 days)."""
    d = daily.filter(pl.col("eod_anchor") & (pl.col("equity") > 1000))
    if d.height < min_days:
        return None
    return float((d["resid"].abs() / d["equity"]).median())
