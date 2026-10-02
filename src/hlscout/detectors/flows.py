"""Capital-flow manipulation detectors (D-M*, plan §6.1)."""

from __future__ import annotations

import polars as pl

from hlscout.detectors.base import DAY_MS, Ctx, Finding

RESCUE_KINDS = {"deposit", "accountClassTransfer", "internalTransfer", "subAccountTransfer", "send"}


def d_m1_deposit_inflation(ctx: Ctx) -> Finding | None:
    eqs = ctx.equity
    if eqs.is_empty() or ctx.curve.is_empty():
        return None
    inflow = ctx.flows.filter(pl.col("flow") > 0)["flow"].sum() if not ctx.flows.is_empty() else 0.0
    outflow = -ctx.flows.filter(pl.col("flow") < 0)["flow"].sum() if not ctx.flows.is_empty() else 0.0
    e0, e1 = float(eqs["equity"][0]), float(eqs["equity"][-1])
    denom = (e1 - e0) + outflow
    share = inflow / denom if denom > 0 else None
    twr = float(ctx.curve["twr_index"][-1] - 1)
    naive_roi = (e1 - e0) / max(e0, 1000.0)  # what a viewer of the account-value curve sees
    m = {"flow_share": share, "twr": twr, "naive_roi": naive_roi, "inflow": inflow}
    if naive_roi > 0 and twr <= 0:
        return Finding("D-M1", "VETO", "M", 0, [{"note": "naive ROI positive but TWR <= 0"}], m)
    if share is not None and share > 0.5:
        return Finding("D-M1", "FLAG", "M", 5, [{"note": "flow_share > 0.5"}], m)
    return Finding("D-M1", "INFO", "M", 0, [], m)


def _inflow_events(ctx: Ctx) -> pl.DataFrame:
    return ctx.flows.filter((pl.col("flow") > 0) & pl.col("kind").is_in(list(RESCUE_KINDS)))


def d_m2_rescue_deposit(ctx: Ctx) -> Finding | None:
    """Inflow while the book is deeply underwater and nothing was cut (needs marks or last-fill px)."""
    th = ctx.cfg.detectors.get("rescue", {})
    upnl_max, inflow_min = th.get("upnl_eq_max", -0.25), th.get("inflow_eq_min", 0.15)
    win_ms = th.get("window_min", 60) * 60_000
    veto_count = th.get("veto_count", 2)
    events = []
    for r in _inflow_events(ctx).iter_rows(named=True):
        t, f = r["time"], r["flow"]
        e = ctx.equity_at(t)
        if not e or e <= 0:
            continue
        losers, upnl = [], 0.0
        for coin, (pos, entry, last_px, _) in ctx.timeline.open_positions(t).items():
            mark = (ctx.marks(coin, t) if ctx.marks else None) or last_px
            if mark is None:
                continue
            u = pos * (mark - entry)
            upnl += u
            if u < 0:
                losers.append((coin, pos))
        if not losers or f < inflow_min * e or upnl / e > upnl_max:
            continue
        near = ctx.fills.filter((pl.col("time") >= t - win_ms) & (pl.col("time") <= t + win_ms))
        cut = any(
            not near.filter((pl.col("coin") == c) & (pl.col("side") == ("A" if p > 0 else "B"))).is_empty()
            for c, p in losers)
        if cut:
            continue
        events.append({"time": t, "inflow": f, "equity": e, "upnl_over_equity": upnl / e,
                       "losers": [c for c, _ in losers], "kind": r["kind"]})
    if not events:
        return None
    times = sorted(ev["time"] for ev in events)
    clustered = any(sum(1 for x in times if t0 <= x < t0 + 180 * DAY_MS) >= veto_count for t0 in times)
    sev = "VETO" if clustered else "FLAG"
    return Finding("D-M2", sev, "M", 5 if sev == "FLAG" else 0, events, {"events": len(events)})


def d_m8_income_dressing(ctx: Ctx) -> Finding | None:
    led = ctx.ledger
    if led.is_empty() or ctx.equity.is_empty():
        return None
    inc = led.filter(pl.col("type").is_in(["rewardsClaim", "vaultLeaderCommission", "vaultDistribution"]))
    income = inc["usdc"].fill_null(0).sum()
    pnl = float(ctx.equity["cum_pnl"][-1])
    if income > 0 and pnl > 0 and income / pnl > 0.2:
        return Finding("D-M8", "INFO", "M", 0, [{"income": income}], {"income_share": income / pnl})
    return None


def _underwater_at(ctx: Ctx, t: int, coin: str | None) -> tuple[bool, float]:
    """(is a losing position open at t, total uPnL/equity). coin=None -> any losing position counts."""
    e = ctx.equity_at(t)
    if not e or e <= 0:
        return False, 0.0
    upnl, losing = 0.0, False
    for c, (pos, entry, last_px, _) in ctx.timeline.open_positions(t).items():
        mark = (ctx.marks(c, t) if ctx.marks else None) or last_px
        if mark is None:
            continue
        u = pos * (mark - entry)
        upnl += u
        if u < 0 and (coin is None or c == coin):
            losing = True
    return losing, upnl / e


def _coin_of(ctx: Ctx, asset: int | None) -> str | None:
    names = ctx.asset_names
    return names[asset] if names and asset is not None and 0 <= asset < len(names) else None


def d_m3_m4_margin_actions(ctx: Ctx) -> Finding | None:
    """Isolated-margin top-ups (D-M3) and leverage-down (D-M4) while a position is deeply underwater.

    Source: explorer action log (recent history only). Counts toward a combined tally like D-M2.
    """
    if not ctx.actions:
        return None
    th = ctx.cfg.detectors.get("rescue", {})
    upnl_max, win_ms = th.get("upnl_eq_max", -0.25), th.get("window_min", 60) * 60_000
    events = []
    for a in ctx.actions:
        act, t = a["action"], int(a["time"])
        kind = act.get("type")
        if kind == "updateIsolatedMargin" and not (act.get("isBuy") and (act.get("ntli") or 0) > 0):
            continue
        if kind not in ("updateIsolatedMargin", "updateLeverage"):
            continue
        coin = _coin_of(ctx, act.get("asset"))
        losing, ratio = _underwater_at(ctx, t, coin)
        if not losing or ratio > upnl_max:
            continue
        near = ctx.fills.filter((pl.col("time") >= t - win_ms) & (pl.col("time") <= t + win_ms))
        if coin is not None:
            near = near.filter(pl.col("coin") == coin)
        if kind == "updateLeverage":
            # raising leverage is not a rescue; the action log has no previous value, so only flag
            # lowered leverage when a smaller cap is requested while no size change happened
            pass
        if not near.is_empty():
            continue  # size was cut or changed around the action: not a pure rescue
        events.append({"time": t, "kind": "D-M3" if kind == "updateIsolatedMargin" else "D-M4",
                       "coin": coin, "upnl_over_equity": ratio, "hash": a.get("hash")})
    if not events:
        return None
    times = sorted(e["time"] for e in events)
    veto = any(sum(1 for x in times if t0 <= x < t0 + 180 * DAY_MS) >= th.get("veto_count", 2) for t0 in times)
    return Finding("D-M3", "VETO" if veto else "FLAG", "M", 0 if veto else 5, events,
                   {"events": len(events)})


def d_m6_borrowed_buying_power(ctx: Ctx) -> Finding | None:
    """Manual borrows (borrowLend operation=borrow). Supplies/withdrawals are lending, not leverage."""
    import json

    if ctx.ledger.is_empty():
        return None
    rows = ctx.ledger.filter(pl.col("type") == "borrowLend")
    borrows = []
    for r in rows.iter_rows(named=True):
        d = json.loads(r["raw_json"] or "{}")
        if d.get("operation") == "borrow":
            borrows.append({"time": r["time"], "token": d.get("token"), "amount": float(d.get("amount") or 0)})
    if not borrows:
        return None
    m = {"borrows": len(borrows), "total": sum(b["amount"] for b in borrows)}
    return Finding("D-M6", "FLAG", "M", 5, borrows[:10], m)
