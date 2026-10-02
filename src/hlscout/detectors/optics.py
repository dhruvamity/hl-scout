"""Statistical / optical detectors (D-C*, plan §6.4)."""

from __future__ import annotations

import polars as pl

from hlscout.detectors.base import Ctx, Finding


def d_c1_board_vs_account(ctx: Ctx) -> Finding | None:
    if not ctx.lb:
        return None
    board = ctx.lb.get("pnl_month")
    pm = ctx.portfolio.get("perpMonth", {}).get("pnlHistory")
    if board is None or not pm:
        return None
    acct = float(pm[-1][1]) - float(pm[0][1])
    m = {"board_pnl_month": board, "account_pnl_month": acct}
    if board > 0 and acct <= 0:
        return Finding("D-C1", "VETO", "C", 0, [m], m)
    return Finding("D-C1", "INFO", "C", 0, [], m)


def trade_concentration(ctx: Ctx) -> dict:
    t = ctx.trips
    if t.is_empty():
        return {}
    net = (t["pnl"] - t["fees"] + t["funding"])
    total = float(net.sum())
    tt = t.with_columns(net.alias("net"), pl.from_epoch("close_ts", time_unit="ms").dt.strftime("%Y-%m").alias("m"))
    out = {"net_total": total}
    if total > 0:
        top5 = float(net.sort(descending=True).head(5).sum())
        out["top5_share"] = top5 / total
        out["top1_share"] = float(net.max()) / total
        months = tt.group_by("m").agg(pl.col("net").sum())
        out["best_month_share"] = float(months["net"].max()) / total
        out["positive_months"] = int((months["net"] > 0).sum())
        out["months"] = months.height
        coins = tt.group_by("coin").agg(pl.col("net").sum())
        out["top_coin_share"] = float(coins["net"].max()) / total
    return out


def d_c2_concentration(ctx: Ctx) -> Finding | None:
    m = trade_concentration(ctx)
    if not m or "top5_share" not in m:
        return None
    g = ctx.cfg.gates
    if g.concentration_mode == "robust":
        net = (ctx.trips["pnl"] - ctx.trips["fees"] + ctx.trips["funding"]).sort(descending=True)
        total = float(net.sum())
        ex5 = total - float(net.head(5).sum())
        top1 = float(net[0]) / total if total > 0 else 0.0
        m = {**m, "ex_top5_net": ex5}
        if ex5 <= 0 and top1 > g.top1_lottery_share:  # one trade (or five) IS the record
            return Finding("D-C2", "VETO", "C", 0, [{"breached": ["lottery"], "top1_share": top1}], m)
        return Finding("D-C2", "INFO", "C", 0, [], m)
    ev = [k for k, lim in (("top5_share", g.top5_trades_share_max), ("best_month_share", g.best_month_share_max))
          if m[k] > lim]
    if ev:
        return Finding("D-C2", "VETO", "C", 0, [{"breached": ev}], m)
    return Finding("D-C2", "INFO", "C", 0, [], m)


def d_c5_funding_farming(ctx: Ctx) -> Finding | None:
    t = ctx.trips
    if t.height < 5:
        return None
    fund = abs(float(t["funding"].sum()))
    direc = abs(float(t["pnl"].sum()))
    med_hold_h = float(((t["close_ts"] - t["open_ts"]) / 3.6e6).median())
    m = {"funding_to_directional": fund / direc if direc else None, "median_hold_h": med_hold_h}
    if direc > 0 and fund / direc > 0.5 and med_hold_h > 8:
        return Finding("D-C5", "FLAG", "C", 5, [m], m)
    return None


def d_c7_beta_not_skill(ctx: Ctx) -> Finding | None:
    """Daily PnL regressed on BTC daily returns: long-only beta in a bull run is not skill.

    Needs hourly BTC marks (ctx.marks) and >= 60 active days; otherwise silent.
    """
    import numpy as np

    from hlscout.detectors.base import DAY_MS

    t = ctx.trips
    if t.is_empty() or ctx.marks is None:
        return None
    d = (t.with_columns(((pl.col("close_ts") // DAY_MS)).alias("d"),
                        (pl.col("pnl") - pl.col("fees") + pl.col("funding")).alias("net"))
         .group_by("d").agg(pl.col("net").sum()).sort("d"))
    if d.height < 60:
        return None
    ys, xs = [], []
    for day, net in zip(d["d"].to_list(), d["net"].to_list(), strict=True):
        a, b = ctx.marks("BTC", day * DAY_MS), ctx.marks("BTC", (day + 1) * DAY_MS - 1)
        if a and b:
            xs.append(b / a - 1)
            ys.append(net)
    if len(xs) < 60:
        return None
    x, y = np.array(xs), np.array(ys)
    X = np.column_stack([np.ones_like(x), x])
    coef, res, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    s2 = resid @ resid / (len(y) - 2)
    cov = s2 * np.linalg.inv(X.T @ X)
    t_alpha = float(coef[0] / np.sqrt(cov[0, 0])) if cov[0, 0] > 0 else 0.0
    long_share = float((t["side"] == "long").mean())
    m = {"alpha_t": t_alpha, "beta": float(coef[1]), "long_share": long_share}
    if t_alpha < 2.0 and long_share > 0.8:
        return Finding("D-C7", "FLAG", "C", 5, [m], m)
    return Finding("D-C7", "INFO", "C", 0, [], m)


def d_c8_event_concentration(ctx: Ctx) -> Finding | None:
    """>= 70% of gross profit inside <= 3 short (3-day) windows. Cannot prove intent: flag only."""
    from hlscout.detectors.base import DAY_MS

    t = ctx.trips
    if t.height < 30:
        return None
    t = t.with_columns((pl.col("pnl") - pl.col("fees") + pl.col("funding")).alias("net"))
    wins = t.filter(pl.col("net") > 0)
    total = float(wins["net"].sum())
    if total <= 0:
        return None
    by_win = (wins.with_columns((pl.col("close_ts") // (3 * DAY_MS)).alias("w"))
              .group_by("w").agg(pl.col("net").sum()).sort("net", descending=True))
    top3 = float(by_win["net"].head(3).sum()) / total
    span_days = (int(t["close_ts"].max()) - int(t["open_ts"].min())) / DAY_MS
    if top3 >= 0.7 and span_days >= 90:
        m = {"top3_window_share": top3, "span_days": span_days}
        return Finding("D-C8", "FLAG", "C", 5, [m], m)
    return None
