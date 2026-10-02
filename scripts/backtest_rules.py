"""Pseudo-forward backtest of the integrity rules (audit: calibrate with evidence, not opinion).

For each wallet, features are computed using ONLY data before a cutoff T (fills, equity, ledger up to T). Outcomes are
measured after T. If a rule flags a wallet but flagged wallets do no worse afterwards than unflagged ones, the rule is
not earning its veto. Run: uv run python scripts/backtest_rules.py [--days 120] [--out docs/BACKTEST_RULES.md]
Caveat printed in the report: the pool is leaderboard survivors, so everything regresses towards the mean.
"""
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from hlscout.config import load_config
from hlscout.recon.vet import load_raw, make_ctx
from hlscout.scoring.consistency import compute_metrics

DAY = 86_400_000
days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 120
out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
cfg = load_config()
root = Path("data")
now = int(time.time() * 1000)
T = now - days * DAY
rows = []
files = sorted((root / "raw" / "fills").glob("*.parquet"))
for i, fp in enumerate(files):
    a = fp.stem
    try:
        raw = load_raw(root, a)
        full = make_ctx(a, {**raw, "now_ms": now}, cfg)
    except Exception:
        continue
    if full.fills.is_empty() or full.trips.is_empty():
        continue
    first = int(full.fills["time"].min())
    if T - first < 120 * DAY:        # need >= 120 d of pre-history
        continue
    pre_raw = {**raw, "fills": raw["fills"].filter(pl.col("time") < T), "now_ms": T}
    try:
        pre = make_ctx(a, pre_raw, cfg)
        if pre.trips.height < 40:
            continue
        m = compute_metrics(pre, 500)
    except Exception:
        continue
    t = pre.trips
    net = (t["pnl"] - t["fees"] + t["funding"])
    mart = t.filter((pl.col("adds") > 0) & (pl.col("underwater_add_share") > 0.5) & (pl.col("first_clip") > 0)
                    & (pl.col("max_size") / pl.col("first_clip") >= 3))
    mr = m.get("month_reasons", {})
    # alternative month-level martingale rule: month is martingale-heavy only if > 35% of its trips are
    tm = t.with_columns(pl.col("close_ts").map_elements(lambda x: time.strftime("%Y-%m", time.gmtime(x / 1000)),
                                                       return_dtype=pl.Utf8).alias("mo"),
                        ((pl.col("adds") > 0) & (pl.col("underwater_add_share") > 0.5) & (pl.col("first_clip") > 0)
                         & (pl.col("max_size") / pl.col("first_clip") >= 3)).alias("is_mart"))
    mshare = tm.group_by("mo").agg(pl.col("is_mart").mean().alias("s"), pl.len().alias("n")).filter(pl.col("n") >= 5)
    mart35 = float((mshare["s"] > 0.35).mean()) if mshare.height else 0.0
    active = max(1, m.get("active_months", 1))
    post = full.trips.filter(pl.col("close_ts") >= T)
    if post.height < 20:
        continue
    pnet = float((post["pnl"] - post["fees"] + post["funding"]).sum())
    eq = pre.equity_at(T) or float(pre.equity["equity"].median())
    eq = max(eq, 1000.0)
    d = full.daily.filter(pl.col("time") >= T) if full.daily is not None and not full.daily.is_empty() else None
    dd_post = 0.0
    if d is not None and not d.is_empty():
        idx = (1 + d["r"]).cum_prod()
        dd_post = float((1 - idx / idx.cum_max()).max())
    rows.append({
        "address": a, "n_pre": t.height, "n_post": post.height,
        "mart_freq": mart.height / t.height, "mart_months": mr.get("martingale", 0) / active, "mart35": mart35,
        "dd_months": mr.get("dd", 0) / active, "lev25_months": mr.get("leverage>25x", 0) / active,
        "liq_pre": int(t["liquidated"].sum()), "net_pre": float(net.sum()),
        "ret_post": pnet / eq, "net_post": pnet, "dd_post": dd_post,
        "liq_post": bool(post["liquidated"].any()),
    })
    if len(rows) % 25 == 0:
        print(f"{len(rows)} wallets backtested ({i + 1}/{len(files)} scanned)", file=sys.stderr)
df = pl.DataFrame(rows).with_columns(
    ((pl.col("net_post") <= 0) | pl.col("liq_post") | (pl.col("dd_post") > 0.30)).alias("bad"))


def boot_diff(a: np.ndarray, b: np.ndarray, n: int = 2000, seed: int = 1) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    d = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(n)]
    return float(np.percentile(d, 5)), float(np.percentile(d, 95))


def table(feature: str, edges: list[float], labels: list[str]) -> list[str]:
    lines = [f"| {feature} | wallets | profitable after | median return after | share 'bad' after | liquidated after |",
             "|---|---|---|---|---|---|"]
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels, strict=True):
        g = df.filter((pl.col(feature) >= lo) & (pl.col(feature) < hi))
        if g.height:
            lines.append(f"| {lab} | {g.height} | {float((g['net_post'] > 0).mean()):.0%} | "
                         f"{float(g['ret_post'].median()):+.1%} | {float(g['bad'].mean()):.0%} | {float(g['liq_post'].mean()):.0%} |")
    return lines


L = [f"# Backtest of integrity rules (cutoff = {days} days ago)", "",
     f"Wallets with >= 120 d of history before the cutoff, >= 40 round trips before and >= 20 after: **{df.height}**. "
     "Features use only data before the cutoff; outcomes are measured after it. 'bad' = lost money, or liquidated, or "
     "drawdown > 30% in the period after.", "",
     "Caveat: the pool is leaderboard survivors, so outcomes regress towards the mean for every group; "
     "compare groups with each other, not with zero.", ""]
L += ["## Martingale frequency (share of round trips that scaled into a loser >= 3x), D-R1 vetoes above 10%", ""]
L += table("mart_freq", [0, 0.02, 0.10, 0.25, 1.01], ["< 2%", "2-10%", "10-25% (veto zone)", "> 25%"]) + [""]
L += ["## Months with a martingale-heavy share of trips (drives G1b)", ""]
L += table("mart_months", [0, 0.01, 0.34, 0.67, 1.01], ["no such month", "up to a third of months", "a third to two thirds", "most months"]) + [""]
L += ["## Stricter month rule: months where > 35% of trips are martingale-like", ""]
L += table("mart35", [0, 0.01, 0.34, 1.01], ["no such month", "up to a third of months", "more than a third of months"]) + [""]
L += ["## Months with in-month drawdown > 30% (drives G1b)", ""]
L += table("dd_months", [0, 0.01, 0.25, 0.5, 1.01], ["none", "< 25% of months", "25-50% of months", "> 50% of months"]) + [""]
L += ["## Months with a trip above 25x leverage", ""]
L += table("lev25_months", [0, 0.01, 0.25, 1.01], ["none", "< 25% of months", ">= 25% of months"]) + [""]
L += ["## Liquidations before the cutoff (G9)", ""]
df = df.with_columns(pl.col("liq_pre").clip(0, 3).cast(pl.Float64).alias("liq_pre_c"))
L += table("liq_pre_c", [0, 1, 2, 3.5], ["0", "1", "2+"]) + [""]

L += ["## Does each rule separate outcomes? (flagged minus unflagged, 90% bootstrap interval; negative = flagged wallets did worse)", "",
      "| Rule | flagged | unflagged | return after: flagged - unflagged | 'bad' rate: flagged - unflagged |", "|---|---|---|---|---|"]
for name, expr in (("martingale freq > 10% (D-R1 veto)", pl.col("mart_freq") > 0.10),
                   ("any month with martingale-heavy trips", pl.col("mart_months") > 0),
                   ("any month with > 35% martingale-like trips", pl.col("mart35") > 0),
                   (">= 1/3 of months with > 35% martingale-like trips", pl.col("mart35") >= 0.34),
                   ("any month with in-month DD > 30%", pl.col("dd_months") > 0),
                   (">= 25% of months with DD > 30%", pl.col("dd_months") >= 0.25),
                   ("any month with > 25x leverage", pl.col("lev25_months") > 0),
                   ("liquidated before cutoff", pl.col("liq_pre") > 0)):
    f, u = df.filter(expr), df.filter(~expr)
    if f.height >= 8 and u.height >= 8:
        lo, hi = boot_diff(f["ret_post"].clip(-1, 2).to_numpy(), u["ret_post"].clip(-1, 2).to_numpy())
        blo, bhi = boot_diff(f["bad"].cast(pl.Float64).to_numpy(), u["bad"].cast(pl.Float64).to_numpy())
        L.append(f"| {name} | {f.height} | {u.height} | [{lo:+.1%}, {hi:+.1%}] | [{blo:+.0%}, {bhi:+.0%}] |")
    else:
        L.append(f"| {name} | {f.height} | {u.height} | n/a | n/a |")
text = "\n".join(L) + "\n"
print(text)
if out_path:
    Path(out_path).write_text(text)
