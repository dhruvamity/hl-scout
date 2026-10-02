"""Full-history consistency and discipline metrics (plan §7)."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import polars as pl

from hlscout.detectors.base import DAY_MS, Ctx
from hlscout.detectors.flows import d_m2_rescue_deposit
from hlscout.detectors.risk import trip_leverage
from hlscout.recon import equity as eq
from hlscout.scoring.dsr import deflated_sharpe_prob, tstat

MIN_ACTIVE_DAYS_MONTH = 4


def month_of(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m")


def months_between(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _trip_frame(ctx: Ctx) -> pl.DataFrame:
    t = ctx.trips
    if t.is_empty():
        return t
    lev = trip_leverage(ctx)
    t = t.join(lev.select(["open_ts", "lev"]), on="open_ts", how="left")
    return t.with_columns(
        (pl.col("pnl") - pl.col("fees") + pl.col("funding")).alias("net"),
        pl.col("close_ts").map_elements(month_of, return_dtype=pl.Utf8).alias("month"),
        ((pl.col("close_ts") - pl.col("open_ts")) / 1000).alias("hold_s"),
        ((pl.col("underwater_add_share") > 0.5) & (pl.col("first_clip") > 0)
         & (pl.col("max_size") / pl.col("first_clip").clip(1e-12) >= 3)).alias("martingale"),
    )


def grade_months(ctx: Ctx, tf: pl.DataFrame) -> pl.DataFrame:
    """One row per month from the first fill: genuine | violation | inactive | unknown (§7.0)."""
    if ctx.fills.is_empty():
        return pl.DataFrame(schema={"month": pl.Utf8, "grade": pl.Utf8})
    first = month_of(int(ctx.fills["time"].min()))
    last = month_of(ctx.now_ms)
    coarse_rows = _coarse_months(ctx, first)
    gate_dd = ctx.cfg.gates.max_dd_twr
    days = (ctx.fills.with_columns((pl.col("time") // DAY_MS).alias("d"),
                                   pl.col("time").map_elements(month_of, return_dtype=pl.Utf8).alias("m"))
            .group_by("m").agg(pl.col("d").n_unique().alias("active_days")))
    active = dict(zip(days["m"], days["active_days"], strict=True))
    rescue = d_m2_rescue_deposit(ctx)
    rescue_months = {month_of(e["time"]) for e in (rescue.evidence if rescue else [])}
    liq_months = set(ctx.ledger.filter(pl.col("type") == "liquidation")["time"].map_elements(
        month_of, return_dtype=pl.Utf8).to_list()) if not ctx.ledger.is_empty() else set()
    cv = ctx.curve.with_columns(pl.col("time").map_elements(month_of, return_dtype=pl.Utf8).alias("m"))
    rows = []
    for m in months_between(first, last):
        ad = active.get(m, 0)
        if ad < MIN_ACTIVE_DAYS_MONTH:
            rows.append({"month": m, "grade": "inactive", "reasons": ""})
            continue
        sub = tf.filter(pl.col("month") == m) if not tf.is_empty() else tf
        reasons = []
        if not sub.is_empty():
            if sub["liquidated"].any() or m in liq_months:
                reasons.append("liquidation")
            if sub["martingale"].any() and sub["martingale"].mean() > 0.10:
                reasons.append("martingale")
            if (sub["lev"].fill_null(0) > 25).any():
                reasons.append("leverage>25x")
            if not sub["complete"].all():
                reasons.append("unknown")
        if m in rescue_months:
            reasons.append("rescue")
        mc = cv.filter(pl.col("m") == m)
        if not mc.is_empty() and 1 - (mc["twr_index"] / mc["twr_index"].cum_max()).min() > gate_dd:
            reasons.append("dd")
        grade = ("unknown" if reasons == ["unknown"] else "violation" if reasons else "genuine")
        rows.append({"month": m, "grade": grade, "reasons": ",".join(reasons)})
    return pl.DataFrame(coarse_rows + rows, schema={"month": pl.Utf8, "grade": pl.Utf8, "reasons": pl.Utf8})


def _coarse_months(ctx: Ctx, first_fill_month: str) -> list[dict]:
    """Months before the fill record starts, graded from portfolio equity + ledger flows only (§7.0.8).

    Only emitted when the caller set `ctx.coarse_ok` (archive coverage was tried and ends here).
    A coarse month is 'coarse' (counts toward tenure) when inflows are small against the month's
    opening equity and the TWR-style drawdown stays inside the gate; otherwise 'violation'.
    """
    if not getattr(ctx, "coarse_ok", False) or ctx.equity.is_empty():
        return []
    start = month_of(int(ctx.equity["time"].min()))
    if start >= first_fill_month:
        return []
    rows = []
    fl = ctx.flows.with_columns(pl.col("time").map_elements(month_of, return_dtype=pl.Utf8).alias("m")) \
        if not ctx.flows.is_empty() else ctx.flows
    ev = ctx.equity.with_columns(pl.col("time").map_elements(month_of, return_dtype=pl.Utf8).alias("m"))
    for m in months_between(start, first_fill_month)[:-1]:
        sub = ev.filter(pl.col("m") == m)
        if sub.is_empty():
            rows.append({"month": m, "grade": "inactive", "reasons": ""})
            continue
        e0 = float(sub["equity"][0])
        inflow = float(fl.filter((pl.col("m") == m) & (pl.col("flow") > 0))["flow"].sum()) \
            if not fl.is_empty() else 0.0
        peak = sub["equity"].cum_max()
        dd = float((1 - sub["equity"] / peak).max())
        net_flow = float(fl.filter(pl.col("m") == m)["flow"].sum()) if not fl.is_empty() else 0.0
        month_pnl = float(sub["equity"][-1]) - e0 - net_flow      # equity change not explained by flows
        # capital added is normal growth UNLESS it arrives while losing (the coarse-resolution rescue signature)
        rescue_like = inflow > 0.25 * max(e0, 1000.0) and (month_pnl <= 0 or dd > 0.15)
        bad = rescue_like or dd > ctx.cfg.gates.max_dd_twr + 0.2
        rows.append({"month": m, "grade": "violation" if bad else "coarse",
                     "reasons": ("coarse_rescue" if rescue_like else "coarse_dd") if bad else ""})
    return rows


def compute_metrics(ctx: Ctx, n_trials: int = 5000) -> dict:
    tf = _trip_frame(ctx)
    g = ctx.cfg.gates
    now = ctx.now_ms
    out: dict = {"n_trips": tf.height}
    if tf.is_empty():
        return out
    months = grade_months(ctx, tf)
    out["months"] = months
    first_fill = int(ctx.fills["time"].min())
    out["track_days"] = (now - first_fill) / DAY_MS
    cur = month_of(now)  # the current (partial) month is excluded: last 6 *complete* months
    last6 = [m for m in months_between(month_of(now - 215 * DAY_MS), cur) if m < cur][-6:]
    mg = dict(zip(months["month"], months["grade"], strict=True))
    out["active_last6"] = sum(1 for m in last6 if mg.get(m) not in (None, "inactive"))
    graded = months.filter(pl.col("grade") != "inactive")
    n_active = graded.height
    n_gen = int(graded["grade"].is_in(["genuine", "coarse"]).sum())
    out["coarse_months"] = int((graded["grade"] == "coarse").sum())
    n_unknown = int((graded["grade"] == "unknown").sum())
    out.update(genuine_months=n_gen, active_months=n_active,
               genuine_coverage=n_gen / max(1, n_active - n_unknown))
    seq = [x for x in months["grade"].to_list() if x != "inactive"]
    out["first_genuine_idx"] = next((i for i, x in enumerate(seq) if x in ("genuine", "coarse")), None)
    # last 180d window
    w0 = now - 180 * DAY_MS
    t180 = tf.filter(pl.col("close_ts") >= w0)
    out["net_180d"] = float(t180["net"].sum()) if not t180.is_empty() else 0.0
    out["net_all"] = float(tf["net"].sum())
    # regularity
    fd = ctx.fills.filter(pl.col("time") >= w0).with_columns((pl.col("time") // DAY_MS).alias("d"))
    days_set = sorted(set(fd["d"].to_list()))
    weeks: dict[int, set] = {}
    for d in days_set:
        weeks.setdefault(d // 7, set()).add(d)
    all_weeks = range(w0 // DAY_MS // 7, now // DAY_MS // 7 + 1)
    out["weekly_coverage"] = sum(1 for w in all_weeks if len(weeks.get(w, ())) >= 3) / len(all_weeks)
    gaps = [b - a for a, b in zip(days_set, days_set[1:], strict=False)]
    edge = [days_set[0] - w0 // DAY_MS, now // DAY_MS - days_set[-1]] if days_set else [180]
    out["max_gap_days"] = max(gaps + edge) if (gaps or edge) else 180
    # intraday
    out["median_hold_s"] = float(tf["hold_s"].median())
    out["intraday_close_share"] = float((tf["hold_s"] <= 86_400).mean())
    out["avg_hold_s"] = float(tf["hold_s"].mean())
    # monthly pnl / concentration over last 180d
    if not t180.is_empty():
        mm = t180.group_by("month").agg(pl.col("net").sum()).sort("month")
        out["positive_months_last6"] = int((mm["net"] > 0).sum())
        out["best_month_share"] = (float(mm["net"].max()) / out["net_180d"]) if out["net_180d"] > 0 else None
        out["top5_share"] = (float(t180["net"].sort(descending=True).head(5).sum()) / out["net_180d"]
                             if out["net_180d"] > 0 else None)
    # robust concentration (audit C3): would the record survive without its best 5 trades / best month?
    def _conc(frame: pl.DataFrame, tag: str) -> None:
        if frame.is_empty():
            return
        net = frame["net"].sort(descending=True)
        tot = float(net.sum())
        gross_win = float(net.filter(net > 0).sum())
        out[f"ex_top5_net_{tag}"] = tot - float(net.head(5).sum())
        out[f"top5_gross_share_{tag}"] = float(net.filter(net > 0).head(5).sum()) / gross_win if gross_win > 0 else None
        out[f"top1_net_share_{tag}"] = float(net[0]) / tot if tot > 0 else None
        mo = frame.group_by("month").agg(pl.col("net").sum())
        pos = float(mo.filter(pl.col("net") > 0)["net"].sum())
        out[f"best_month_pos_share_{tag}"] = float(mo["net"].max()) / pos if pos > 0 else None

    _conc(tf, "all")
    _conc(t180, "180d")
    # terciles (full history)
    if tf.height >= 30:
        s = tf.sort("close_ts")["net"].to_numpy()
        out["tercile_net"] = [float(x.sum()) for x in np.array_split(s, 3)]
    # returns / edge
    daily = eq.daily_returns(ctx.curve)
    r = daily["r"].to_numpy()
    out["n_daily"] = len(r)
    out["twr_all"] = float(ctx.curve["twr_index"][-1] - 1) if not ctx.curve.is_empty() else None
    c180 = ctx.curve.filter(pl.col("time") >= w0)
    out["twr_180d"] = float((1 + c180["r"]).product() - 1) if not c180.is_empty() else None
    out["max_dd_twr"] = eq.max_drawdown(ctx.curve)
    out["sharpe"] = eq.sharpe(daily)
    neg = r[r < 0]
    out["sortino"] = float(r.mean() / neg.std(ddof=1) * np.sqrt(365)) if len(neg) > 2 and neg.std(ddof=1) > 0 else 0.0
    out["tstat"] = tstat(r)
    out["dsr_prob"] = deflated_sharpe_prob(r, n_trials)
    # rolling 90-day TWR positivity
    if not ctx.curve.is_empty():
        c = ctx.curve.with_columns((pl.col("time") // DAY_MS).alias("d"))
        idx = c.group_by("d").agg(pl.col("twr_index").last()).sort("d")
        d, v = idx["d"].to_numpy(), idx["twr_index"].to_numpy()
        wins = [v[i] / v[j] - 1 for i in range(len(d)) for j in [np.searchsorted(d, d[i] - 90)]
                if d[i] - d[0] >= 90 and j < i]
        out["rolling90_positive"] = float(np.mean([w > 0 for w in wins])) if wins else None
    # profit factor / payoff
    wins_, losses_ = tf.filter(pl.col("net") > 0)["net"], tf.filter(pl.col("net") < 0)["net"]
    out["profit_factor"] = float(wins_.sum() / abs(losses_.sum())) if losses_.sum() != 0 else None
    out["payoff"] = float(wins_.mean() / abs(losses_.mean())) if wins_.len() and losses_.len() else None
    out["win_rate"] = float((tf["net"] > 0).mean())
    ent = tf.filter(pl.col("open_notional") > 0)  # notional-weighted: sum(net) / sum(entered notional)
    out["expectancy_bps"] = float(ent["net"].sum() / ent["open_notional"].sum() * 1e4) if ent.height else None
    if ctx.daily is not None and not ctx.daily.is_empty():
        dl = ctx.daily.filter(pl.col("lev") > 0)["lev"]
        if dl.len() >= 20:  # account-level gross notional / equity per day (time-weighted proxy for G8)
            out["lev_daily_p95"] = float(dl.quantile(0.95))
            out["lev_daily_max"] = float(dl.max())
    lv = trip_leverage(ctx)
    out["lev_p95"] = float(lv["lev"].quantile(0.95)) if lv.height >= 5 else None
    out["median_equity"] = float(ctx.equity["equity"].median()) if not ctx.equity.is_empty() else 0.0
    return out
