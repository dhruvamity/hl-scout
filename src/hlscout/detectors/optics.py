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
