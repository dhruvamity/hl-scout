"""HFT/MM, vault, blacklist and manual-vs-algo classification (D-B*, plan §6.5)."""

from __future__ import annotations

import math

import polars as pl

from hlscout.detectors.base import DAY_MS, Ctx, Finding

BLACKLIST = {  # compendium §10 (labels are analysts' claims, used as calibration only)
    "0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00": "mm_hedge",
    "0x5b5d51203a0f9079f8aeb098a6523a13f298c060": "carry_hedge",
    "0xb83de012dba672c76a7dbbbf3e459cb59d7d6e36": "carry_hedge",
    "0x92ea19ecEb7a8de0f50978a1583a5d8b018050e9".lower(): "net_loser",
    "0x0ddf9bae2af4b874b96d287a5ad42eb47138a902": "liquidated",
    "0x020ca66c30bec2c4fe3861a94e4db4a498a35872": "lifetime_loser",
    "0xb7e0b9fbc9479330d70bcc82a7d4325a20e8d1aa": "hft_mm",
    "0x77375a8c9d13bf79afb2a87f1b0ac1dfd5f5bf66": "many_liquidations",
}


def d_b1_hft_mm(ctx: Ctx) -> Finding | None:
    g = ctx.cfg.gates
    f, t = ctx.fills, ctx.trips
    if f.is_empty():
        return None
    days = max(1, f.select((pl.col("time") // DAY_MS).n_unique()).item())
    tpd = f.height / days
    maker = float((f["crossed"] == False).sum()) / f.height
    avg_hold = float(((t["close_ts"] - t["open_ts"]) / 1000).mean()) if not t.is_empty() else None
    m = {"trades_per_active_day": tpd, "maker_share": maker, "avg_hold_s": avg_hold}
    reasons = []
    if avg_hold is not None and avg_hold < g.hft_avg_hold_min_s:
        reasons.append("avg_hold")
    if maker > g.maker_share_max:
        reasons.append("maker_share")
    if tpd > g.trades_per_day_max:
        reasons.append("trades_per_day")
    if reasons:
        return Finding("D-B1", "VETO", "B", 0, [{"reasons": reasons}], m)
    return Finding("D-B1", "INFO", "B", 0, [], m)


def d_b3_vault_protocol(ctx: Ctx) -> Finding | None:
    role = (ctx.role or {}).get("role")
    if ctx.address.startswith("0x4000000000000000000000000000000000000") or role in ("vault", "agent"):
        return Finding("D-B3", "VETO", "B", 0, [{"role": role}], {"role": role})
    if role == "subAccount":
        return Finding("D-B3", "INFO", "B", 0, [{"note": "sub-account: score the master book"}], {"role": role})
    return None


def d_b5_blacklist(ctx: Ctx) -> Finding | None:
    if ctx.address in BLACKLIST:
        return Finding("D-B5", "VETO", "B", 0, [{"label": BLACKLIST[ctx.address]}], {})
    return None


def d_b6_twap(ctx: Ctx) -> Finding | None:
    t = ctx.trips
    if t.is_empty():
        return None
    share = float((t["twap_share"] * t["max_size"]).sum() / max(t["max_size"].sum(), 1e-9))
    if share > 0.4:
        return Finding("D-B6", "FLAG", "B", 5, [{"twap_share": share}], {"twap_share": share})
    return None


def classify_algo(ctx: Ctx) -> dict:
    """D-B2: p_algo in [0,1] from timing/size features. Weights are placeholders to calibrate (§16 Q6)."""
    f = ctx.fills
    if f.height < 50:
        return {"p_algo": 0.5, "category": "UNSURE", "features": {}}
    hours = (f["time"] // 3_600_000 % 24).to_list()
    counts = [hours.count(h) for h in range(24)]
    total = sum(counts)
    probs = [c / total for c in counts if c]
    entropy = -sum(p * math.log(p) for p in probs) / math.log(24)  # 1.0 = perfectly flat
    quiet = [c / total < 0.01 for c in counts]
    longest = max((len(list(g)) for k, g in __import__("itertools").groupby(quiet + quiet) if k), default=0)
    sleep_gap_h = min(longest, 24)
    orders = f.group_by("oid").agg(pl.col("time").min().alias("t"), pl.col("sz").sum().alias("sz"))
    gaps = orders.sort("t")["t"].diff().drop_nulls()
    sub_second = float((gaps < 1000).mean()) if gaps.len() else 0.0
    modal = orders["sz"].round(6).value_counts().sort("count", descending=True)
    modal_share = float(modal["count"][0] / orders.height)
    rl = ctx.rate_limit or {}
    spam = (rl.get("nRequestsUsed", 0) / max(f.height, 1)) if rl else None
    feats = {"hour_entropy": entropy, "sleep_gap_h": sleep_gap_h, "sub_second_share": sub_second,
             "modal_size_share": modal_share, "request_per_fill": spam,
             "has_agents": bool(ctx.extra_agents)}
    score = 0.0
    score += 2.0 * (entropy - 0.8) / 0.2          # flat 24h profile
    score += 1.5 * (0.5 if sleep_gap_h < 4 else -0.5 if sleep_gap_h >= 6 else 0)
    score += 2.0 * (sub_second - 0.3) / 0.3
    score += 1.0 * (modal_share - 0.3) / 0.3
    if spam is not None:
        score += 1.5 * (min(spam, 30) - 8) / 8
    if feats["has_agents"]:
        score += 0.75
    p = 1 / (1 + math.exp(-score))
    cfg = ctx.cfg.categories
    cat = "ADT" if p >= cfg.algo_p_threshold else "MDT" if p <= cfg.manual_p_threshold else "UNSURE"
    return {"p_algo": p, "category": cat, "features": feats}
