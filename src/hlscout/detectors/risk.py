"""Risk-behaviour detectors (D-R*, plan §6.3)."""

from __future__ import annotations

import numpy as np
import polars as pl

from hlscout.detectors.base import DAY_MS, Ctx, Finding


def _net(trips: pl.DataFrame) -> pl.Series:
    return trips["pnl"] - trips["fees"] + trips["funding"]


def d_r1_martingale(ctx: Ctx) -> Finding | None:
    t = ctx.trips
    if t.is_empty():
        return None
    th = ctx.cfg.detectors.get("martingale", {})
    # Calibrated by backtest (docs/CALIBRATION.md): flagged wallets did not do worse afterwards, so this is a FLAG
    # above 10% and a VETO only for extreme doubling-down books (> 50% of round trips).
    ush, mult = th.get("underwater_add_share", 0.5), th.get("size_multiple", 3)
    fveto, fflag = th.get("freq_veto", 0.50), th.get("freq_flag", 0.10)
    bad = t.filter((pl.col("adds") > 0) & (pl.col("underwater_add_share") > ush)
                   & (pl.col("first_clip") > 0) & (pl.col("max_size") / pl.col("first_clip") >= mult))
    freq = bad.height / t.height
    ev = [{"coin": r["coin"], "open_ts": r["open_ts"], "multiple": r["max_size"] / r["first_clip"]}
          for r in bad.head(20).iter_rows(named=True)]
    m = {"martingale_freq": freq, "n": bad.height}
    if freq > fveto:
        return Finding("D-R1", "VETO", "R", 0, ev, m)
    if freq > fflag:
        return Finding("D-R1", "FLAG", "R", 5, ev, m)
    return None


def d_r2_bag_holding(ctx: Ctx) -> Finding | None:
    t = ctx.trips
    metrics, ev, sev = {}, [], None
    if not t.is_empty():
        net = _net(t)
        dur = (t["close_ts"] - t["open_ts"]).cast(pl.Float64)
        w, l = dur.filter(net > 0), dur.filter(net < 0)
        if w.len() >= 5 and l.len() >= 5 and (w.median() or 0) > 0:
            ratio = l.median() / w.median()
            metrics["loser_winner_hold_ratio"] = ratio
            if ratio > 3:
                sev = "FLAG"
    for s in ctx.states:
        acct = float(s["state"]["marginSummary"]["accountValue"] or 0)
        for p in s["state"]["assetPositions"]:
            pos = p["position"]
            u = float(pos["unrealizedPnl"])
            if acct > 0 and u / acct <= -0.20:
                opened = ctx.timeline.at(pos["coin"], ctx.now_ms)[3]
                age_d = (ctx.now_ms - opened) / DAY_MS if opened else 0
                if age_d > 3:
                    ev.append({"coin": pos["coin"], "upnl_over_equity": u / acct, "age_days": age_d})
                    sev = "VETO" if u / acct <= -0.30 else (sev or "FLAG")
    if sev:
        return Finding("D-R2", sev, "R", 5 if sev == "FLAG" else 0, ev, metrics)
    return None


def d_r3_negative_skew(ctx: Ctx) -> Finding | None:
    t = ctx.trips
    if t.height < 20:
        return None
    net = _net(t).to_numpy()
    wins, losses = net[net > 0], net[net < 0]
    if len(wins) == 0 or len(losses) == 0:
        return None
    win_rate = len(wins) / len(net)
    payoff = wins.mean() / abs(losses.mean())
    sd = net.std()
    skew = float(((net - net.mean()) ** 3).mean() / sd**3) if sd > 0 else 0.0
    k = max(1, int(len(net) * 0.05))
    cvar5 = float(np.sort(net)[:k].mean())
    m = {"win_rate": win_rate, "payoff": payoff, "skew": skew, "cvar5": cvar5,
         "max_loss_over_median_win": float(abs(losses.min()) / np.median(wins))}
    if win_rate > 0.7 and payoff < 0.3 and skew < 0:
        return Finding("D-R3", "FLAG", "R", 5, [m], m)
    return None


def d_r4_liquidations(ctx: Ctx) -> Finding | None:
    g = ctx.cfg.gates
    liq_trips = ctx.trips.filter(pl.col("liquidated")) if not ctx.trips.is_empty() else ctx.trips
    led = ctx.ledger.filter(pl.col("type") == "liquidation") if not ctx.ledger.is_empty() else ctx.ledger
    times = sorted(set(liq_trips["close_ts"].to_list()) | set(led["time"].to_list()))
    # merge events within an hour: one blow-up appears as fills + ledger entry
    events: list[int] = []
    for x in times:
        if not events or x - events[-1] > 3_600_000:
            events.append(x)
    if not events:
        return None
    recent = [x for x in events if x >= ctx.window_start(180)]
    m = {"liquidations_total": len(events), "liquidations_180d": len(recent)}
    ev = [{"time": x} for x in events[-10:]]
    if len(recent) > g.liquidations_window_max or len(events) > 1:
        return Finding("D-R4", "VETO", "R", 0, ev, m)
    return Finding("D-R4", "FLAG", "R", 5, ev, m)


def trip_leverage(ctx: Ctx) -> pl.DataFrame:
    rows = []
    for r in ctx.trips.iter_rows(named=True):
        e = ctx.equity_at(r["open_ts"])
        if e and e >= 100:
            rows.append({"open_ts": r["open_ts"], "lev": r["max_size"] * r["vwap_in"] / e,
                         "size_ratio": r["open_notional"] / e})
    return pl.DataFrame(rows, schema={"open_ts": pl.Int64, "lev": pl.Float64, "size_ratio": pl.Float64})


def d_r5_leverage_spikes(ctx: Ctx) -> Finding | None:
    lv = trip_leverage(ctx)
    if lv.height < 5:
        return None
    gate = ctx.cfg.gates.eff_leverage_tw_max
    p95, p99, mx = (float(lv["lev"].quantile(q)) for q in (0.95, 0.99, 1.0))
    m = {"lev_p95": p95, "lev_p99": p99, "lev_max": mx}
    if p99 > 25:
        return Finding("D-R5", "VETO", "R", 0, [m], m)
    if p99 > 2 * gate:
        return Finding("D-R5", "FLAG", "R", 5, [m], m)
    return Finding("D-R5", "INFO", "R", 0, [], m)


def d_r6_size_inconsistency(ctx: Ctx) -> Finding | None:
    t = ctx.trips.sort("open_ts")
    if t.height < 20:
        return None
    net = _net(t).to_list()
    sizes = []
    for r in t.iter_rows(named=True):
        e = ctx.equity_at(r["open_ts"])
        sizes.append(r["open_notional"] / e if e and e >= 100 else None)
    after_loss = [s for i, s in enumerate(sizes[1:], 1) if s and net[i - 1] < 0]
    after_win = [s for i, s in enumerate(sizes[1:], 1) if s and net[i - 1] > 0]
    if len(after_loss) < 5 or len(after_win) < 5 or np.mean(after_win) == 0:
        return None
    tilt = float(np.mean(after_loss) / np.mean(after_win))
    valid = [s for s in sizes if s]
    m = {"tilt_ratio": tilt, "size_cv": float(np.std(valid) / np.mean(valid))}
    if tilt > 1.5:
        return Finding("D-R6", "FLAG", "R", 5, [m], m)
    return Finding("D-R6", "INFO", "R", 0, [], m)


def d_r7_window_edge_loss_hiding(ctx: Ctx) -> Finding | None:
    """Losses almost never realized in the last 3 days of a month while the book carries open
    unrealized losses at month-end (avoiding leaderboard-roll optics). Needs >= 4 months."""
    t = ctx.trips
    if t.is_empty():
        return None
    from hlscout.scoring.consistency import month_of

    t = t.with_columns((pl.col("pnl") - pl.col("fees") + pl.col("funding")).alias("net"))
    losers = t.filter(pl.col("net") < 0)
    if losers.height < 20:
        return None
    last3 = losers.filter(
        pl.col("close_ts").map_elements(lambda x: _day_of_month(x) >= _days_in_month(x) - 2,
                                        return_dtype=pl.Boolean))
    share = last3.height / losers.height
    months = sorted({month_of(int(x)) for x in t["close_ts"].to_list()})
    if len(months) < 4:
        return None
    bad = 0
    for m in months:
        end = _month_end_ms(m)
        if end > ctx.now_ms:
            continue
        eq = ctx.equity_at(end)
        if not eq:
            continue
        upnl = 0.0
        for c, (pos, entry, last_px, _) in ctx.timeline.open_positions(end).items():
            mk = (ctx.marks(c, end) if ctx.marks else None) or last_px
            if mk:
                upnl += pos * (mk - entry)
        if upnl / eq < -0.05:
            bad += 1
    m = {"last3_loss_share": share, "months_with_open_loss": bad, "months": len(months)}
    if share < 0.03 and bad >= max(2, len(months) // 2):  # expected share ~0.10
        return Finding("D-R7", "FLAG", "R", 5, [m], m)
    return None


def _day_of_month(ms: int) -> int:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ms / 1000, UTC).day


def _days_in_month(ms: int) -> int:
    import calendar
    from datetime import UTC, datetime

    d = datetime.fromtimestamp(ms / 1000, UTC)
    return calendar.monthrange(d.year, d.month)[1]


def _month_end_ms(m: str) -> int:
    import calendar
    from datetime import UTC, datetime

    y, mo = int(m[:4]), int(m[5:])
    return int(datetime(y, mo, calendar.monthrange(y, mo)[1], 23, 59, tzinfo=UTC).timestamp() * 1000)
