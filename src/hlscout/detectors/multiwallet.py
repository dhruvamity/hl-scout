"""Multi-wallet detectors D-H1..H6 and D-M7 (plan §6.2). These need cluster or tape context."""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from hlscout.detectors.base import DAY_MS, Ctx, Finding
from hlscout.recon.positions import Timeline, build_timeline


MAX_TRUSTED_CLUSTER = 12   # larger clusters are probably over-merged: their vetoes are downgraded to FLAGs
MIN_TRUSTED_CONFIDENCE = 0.4


@dataclass
class ClusterCtx:
    cluster_id: str
    members: list[str]
    fills: dict[str, pl.DataFrame]       # perp-only fills per hydrated member
    confidence: float = 1.0              # share of internal edges that are hard / repeated links
    pnl: dict[str, float] = field(default_factory=dict)  # net trading pnl per member
    timelines: dict[str, Timeline] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for a, f in self.fills.items():
            self.timelines.setdefault(a, build_timeline(f))
            self.pnl.setdefault(a, float(f["closed_pnl"].sum() - f["fee"].sum()) if not f.is_empty() else 0.0)


def hedge_ratio(cc: ClusterCtx, min_overlap_ms: int = 60_000) -> tuple[float, dict]:
    """Notional-time weighted 1 - |sum p_i| / sum |p_i| across members, per coin."""
    num = den = 0.0
    per_coin: dict[str, float] = {}
    coins = {c for tl in cc.timelines.values() for c in tl.times}
    for coin in coins:
        holders = [tl for tl in cc.timelines.values() if coin in tl.times]
        if len(holders) < 2:
            # a single holder cannot hedge on this coin, but still counts in the denominator
            for tl in holders:
                ts, st, px = tl.times[coin], tl.state[coin], tl.last_px[coin]
                for i in range(len(ts) - 1):
                    dt = ts[i + 1] - ts[i]
                    den += dt * abs(st[i][0]) * px[i]
            continue
        grid = sorted({t for tl in holders for t in tl.times[coin]})
        hedged = gross = 0.0
        for a, b in zip(grid, grid[1:]):
            dt = b - a
            ps, pxs = [], []
            for tl in holders:
                p, _, px, _ = tl.at(coin, a)
                ps.append(p)
                if px:
                    pxs.append(px)
            if not pxs:
                continue
            px = sum(pxs) / len(pxs)
            g = sum(abs(p) for p in ps) * px
            n = abs(sum(ps)) * px
            gross += dt * g
            hedged += dt * (g - n)
        num += hedged
        den += gross
        per_coin[coin] = hedged / gross if gross else 0.0
    return (num / den if den else 0.0), per_coin


def d_h1_cross_hedge(ctx: Ctx, cc: ClusterCtx | None, threshold: float = 0.3) -> Finding | None:
    if cc is None or len(cc.fills) < 2:
        return None
    hr, per_coin = hedge_ratio(cc)
    m = {"hedge_ratio": hr, "cluster": cc.cluster_id, "members": cc.members}
    if hr > threshold:
        return Finding("D-H1", "VETO", "H", 0, [{"per_coin": dict(sorted(per_coin.items(), key=lambda x: -x[1])[:5])}], m)
    return Finding("D-H1", "INFO", "H", 0, [], m)


def d_h2_pair_hedge(ctx: Ctx, net_gross_max: float = 0.2, min_share: float = 0.4) -> Finding | None:
    """Within one account: long and short coins held together with small net vs gross notional."""
    tl, fills = ctx.timeline, ctx.fills
    if fills.is_empty() or not tl.times:
        return None
    grid = sorted({t - t % 3_600_000 for ts in tl.times.values() for t in ts})
    if len(grid) < 2:
        return None
    hedged_h = total_h = 0
    for t in grid:
        longs = shorts = 0.0
        for c in tl.times:
            p, _, px, _ = tl.at(c, t + 3_599_999)
            if px:
                if p > 0:
                    longs += p * px
                elif p < 0:
                    shorts += -p * px
        gross = longs + shorts
        if gross <= 0:
            continue
        total_h += 1
        if longs > 0 and shorts > 0 and abs(longs - shorts) / gross <= net_gross_max:
            hedged_h += 1
    share = hedged_h / total_h if total_h else 0.0
    if share >= min_share and total_h >= 24:
        return Finding("D-H2", "FLAG", "H", 5, [{"hedged_hours_share": share}], {"share": share})
    return None


def _party_rows(tape: pl.DataFrame) -> pl.DataFrame:
    """One row per (trade, party) with signed notional: + for the buyer, - for the seller."""
    t = tape.with_columns((pl.col("px") * pl.col("sz")).alias("notional"))
    b = t.select("time", "coin", "tid", pl.col("buyer").alias("addr"), pl.col("notional"),
                 pl.lit(1).alias("sgn"), pl.col("seller").alias("cp"))
    s = t.select("time", "coin", "tid", pl.col("seller").alias("addr"), pl.col("notional"),
                 pl.lit(-1).alias("sgn"), pl.col("buyer").alias("cp"))
    return pl.concat([b, s])


def d_h3_wash(ctx: Ctx, tape: pl.DataFrame | None, members: list[str] | None,
              limit: float = 0.05) -> Finding | None:
    """Share of the wallet's tape volume traded against a member of its own cluster."""
    if tape is None or tape.is_empty():
        return None
    me = ctx.address
    mine = tape.filter((pl.col("buyer") == me) | (pl.col("seller") == me))
    if mine.is_empty():
        return None
    vol = float((mine["px"] * mine["sz"]).sum())
    group = {m.lower() for m in (members or [])} - {me}
    self_trades = mine.filter(pl.col("buyer") == pl.col("seller"))
    same = mine.filter(pl.col("buyer").is_in(group) | pl.col("seller").is_in(group)) if group else mine.clear()
    sv = float((same["px"] * same["sz"]).sum()) + float((self_trades["px"] * self_trades["sz"]).sum())
    share = sv / vol if vol else 0.0
    m = {"same_cluster_volume_share": share, "tape_volume": vol}
    if share > limit:
        return Finding("D-H3", "VETO", "H", 0, [{"share": share, "self_trades": self_trades.height}], m)
    return Finding("D-H3", "INFO", "H", 0, [], m) if vol else None


def d_h5_unlinked_twin(ctx: Ctx, tape: pl.DataFrame | None, window_ms: int = 60_000,
                       tol: float = 0.25, min_events: int = 5, min_share: float = 0.2) -> Finding | None:
    """Another address repeatedly trading the opposite way, same coin, within 60 s and +/-25% size."""
    if tape is None or tape.is_empty():
        return None
    me = ctx.address
    p = _party_rows(tape)
    mine = p.filter(pl.col("addr") == me)
    if mine.height < min_events:
        return None
    oth = p.filter((pl.col("addr") != me) & (pl.col("addr") != "")).select(
        "time", "coin", pl.col("addr").alias("other"), pl.col("notional").alias("n2"),
        pl.col("sgn").alias("s2"), pl.col("tid").alias("tid2"))
    mine = mine.with_columns((pl.col("time") // window_ms).alias("bucket"))
    oth = oth.with_columns((pl.col("time") // window_ms).alias("bucket"))
    hits = []
    for shift in (-1, 0, 1):
        j = mine.join(oth.with_columns((pl.col("bucket") - shift).alias("bucket")),
                      on=["coin", "bucket"], suffix="_o")
        hits.append(j)
    j = pl.concat(hits).filter(
        (pl.col("sgn") != pl.col("s2")) & ((pl.col("time") - pl.col("time_o")).abs() <= window_ms)
        & (pl.col("n2") >= pl.col("notional") * (1 - tol)) & (pl.col("n2") <= pl.col("notional") * (1 + tol))
        & (pl.col("other") != pl.col("cp")) & (pl.col("tid") != pl.col("tid2")))
    if j.is_empty():
        return None
    cnt = j.group_by("other").agg(pl.col("tid").n_unique().alias("events")).sort("events", descending=True)
    top = cnt.row(0, named=True)
    share = top["events"] / mine.height
    if top["events"] >= min_events and share >= min_share:
        return Finding("D-H5", "FLAG", "H", 10, [{"twin": top["other"], "events": top["events"]}],
                       {"twin_share": share})
    return None


def d_b4_copier(ctx: Ctx, tape: pl.DataFrame | None, lo_ms: int = 5_000, hi_ms: int = 120_000,
                min_share: float = 0.7, min_trades: int = 20) -> Finding | None:
    """>= 70% of the wallet's trades follow one specific address's same-side trade by 5-120 s."""
    if tape is None or tape.is_empty():
        return None
    me = ctx.address
    p = _party_rows(tape)
    mine = p.filter(pl.col("addr") == me).unique(subset=["tid"])
    if mine.height < min_trades:
        return None
    oth = p.filter((pl.col("addr") != me) & (pl.col("addr") != "")).select(
        pl.col("time").alias("t2"), "coin", pl.col("addr").alias("leader"), pl.col("sgn").alias("s2"),
        pl.col("tid").alias("tid2"))
    m = mine.with_columns((pl.col("time") // hi_ms).alias("b"))
    o = oth.with_columns((pl.col("t2") // hi_ms).alias("b"))
    parts = [m.join(o.with_columns((pl.col("b") - sh).alias("b")), on=["coin", "b"]) for sh in (-1, 0, 1)]
    j = pl.concat(parts).filter(
        (pl.col("sgn") == pl.col("s2")) & ((pl.col("time") - pl.col("t2")) >= lo_ms)
        & ((pl.col("time") - pl.col("t2")) <= hi_ms) & (pl.col("leader") != pl.col("cp")))
    if j.is_empty():
        return None
    top = j.group_by("leader").agg(pl.col("tid").n_unique().alias("n")).sort("n", descending=True).row(0, named=True)
    share = top["n"] / mine.height
    if share >= min_share:
        return Finding("D-B4", "FLAG", "B", 10, [{"leader": top["leader"], "followed": top["n"]}],
                       {"follow_share": share})
    return None


def d_h6_offvenue(ctx: Ctx) -> Finding | None:
    """Proxy for an invisible CEX hedge: funding-dominated PnL with near-constant notional."""
    t, f = ctx.trips, ctx.funding
    if t.is_empty() or f.is_empty():
        return None
    trading = float(t["pnl"].sum() - t["fees"].sum())
    fund = float(f["usdc"].sum())
    gross = abs(trading) + abs(fund)
    if gross <= 0:
        return None
    fshare = abs(fund) / gross
    long_holds = (t["close_ts"] - t["open_ts"]) / DAY_MS
    median_days = float(long_holds.median())
    if fund > 0 and fshare > 0.6 and median_days > 3:
        return Finding("D-H6", "FLAG", "H", 10, [{"funding_share": fshare, "median_hold_d": median_days}],
                       {"funding_share": fshare})
    return None


def d_h4_lottery(ctx: Ctx, cc: ClusterCtx | None, window_days: int = 14) -> Finding | None:
    if cc is None or len(cc.fills) < 3:
        return None
    firsts = {a: int(f["time"].min()) for a, f in cc.fills.items() if not f.is_empty()}
    if ctx.address not in firsts:
        return None
    mine = firsts[ctx.address]
    batch = [a for a, t in firsts.items() if abs(t - mine) <= window_days * DAY_MS]
    if len(batch) < 3:
        return None
    pnls = {a: cc.pnl[a] for a in batch}
    if pnls[ctx.address] <= 0 or sum(1 for v in pnls.values() if v < 0) < 1:
        return None
    agg = sum(pnls.values())
    m = {"batch": len(batch), "own_pnl": pnls[ctx.address], "aggregate_pnl": agg}
    if agg < 0.5 * pnls[ctx.address]:
        return Finding("D-H4", "VETO", "H", 0, [{"batch_pnls": {a[:10]: round(v) for a, v in pnls.items()}}], m)
    return None


def d_m7_rotation(ctx: Ctx, cc: ClusterCtx | None, gap_days: int = 14) -> Finding | None:
    """Wallet A (net loser) goes quiet, linked wallet B starts within 14 days: merge and re-judge."""
    if cc is None or len(cc.fills) < 2 or ctx.address not in cc.fills:
        return None
    me = cc.fills[ctx.address]
    if me.is_empty():
        return None
    start = int(me["time"].min())
    for a, f in cc.fills.items():
        if a == ctx.address or f.is_empty():
            continue
        end_a = int(f["time"].max())
        if cc.pnl[a] < 0 and 0 <= start - end_a <= gap_days * DAY_MS:
            merged = cc.pnl[a] + cc.pnl[ctx.address]
            if merged <= 0:
                return Finding("D-M7", "VETO", "M", 0,
                               [{"predecessor": a, "its_pnl": cc.pnl[a], "merged_pnl": merged}],
                               {"merged_pnl": merged})
            return Finding("D-M7", "FLAG", "M", 5, [{"predecessor": a, "merged_pnl": merged}],
                           {"merged_pnl": merged})
    return None


def run_cluster_detectors(ctx: Ctx, cc: ClusterCtx | None, tape: pl.DataFrame | None) -> list[Finding]:
    out = [d_h1_cross_hedge(ctx, cc), d_h2_pair_hedge(ctx),
           d_h3_wash(ctx, tape, cc.members if cc else None), d_h4_lottery(ctx, cc),
           d_h5_unlinked_twin(ctx, tape), d_b4_copier(ctx, tape), d_h6_offvenue(ctx), d_m7_rotation(ctx, cc)]
    out = [f for f in out if f is not None]
    if cc is not None and (len(cc.members) > MAX_TRUSTED_CLUSTER or cc.confidence < MIN_TRUSTED_CONFIDENCE):
        # an over-merged or weakly-linked cluster must not veto a wallet: demote cluster-derived vetoes to
        # FLAGs for human QA (tape-derived D-H3 is about the wallet's own counterparties and keeps its severity)
        for f in out:
            if f.code in ("D-H1", "D-H4", "D-M7") and f.severity == "VETO":
                f.severity, f.penalty = "FLAG", 5
                f.evidence.append({"demoted": f"cluster size {len(cc.members)}, confidence {cc.confidence:.2f}"})
    return out
