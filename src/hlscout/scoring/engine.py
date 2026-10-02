"""Decision engine: gates G1-G12, stages, category, per-category ranking (plan §8)."""

from __future__ import annotations

from typing import Any

from hlscout.detectors import run_all, verdict
from hlscout.detectors.automation import classify_algo
from hlscout.detectors.base import Ctx
from hlscout.scoring.consistency import compute_metrics

NOT_EVALUATED = None


def _g(name: str, value: Any, threshold: Any, ok: bool | None) -> dict:
    return {"gate": name, "value": value, "threshold": threshold, "pass": ok}


def evaluate_gates(ctx: Ctx, m: dict, findings: list, cat: dict) -> list[dict]:
    g = ctx.cfg.gates
    h = ctx.cfg.history
    vetoes = [f.code for f in findings if f.severity == "VETO"]
    gates = []
    gates.append(_g("G1 track record", f"{m.get('track_days', 0):.0f}d, active_last6={m.get('active_last6')}",
                    f">={g.min_track_days}d, {g.min_active_months_of_last6}/6",
                    m.get("track_days", 0) >= g.min_track_days
                    and m.get("active_last6", 0) >= g.min_active_months_of_last6))
    fgi = m.get("first_genuine_idx")
    reformed = fgi is None or fgi > h.genuine_start_max_month - 1
    gates.append(_g("G1b genuine throughout",
                    f"coverage={m.get('genuine_coverage', 0):.2f}, first_genuine_idx={fgi}, vetoes={vetoes}",
                    f"cov>={h.genuine_coverage_min}, start<=month{h.genuine_start_max_month}, no veto",
                    m.get("genuine_coverage", 0) >= h.genuine_coverage_min and not reformed
                    and not vetoes))
    gates.append(_g("G2 regularity", f"weekly={m.get('weekly_coverage', 0):.2f}, gap={m.get('max_gap_days')}d",
                    f">={g.weekly_coverage_min}, gap<={g.max_gap_days}d",
                    m.get("weekly_coverage", 0) >= g.weekly_coverage_min
                    and (m.get("max_gap_days") or 999) <= g.max_gap_days))
    gates.append(_g("G3 intraday", f"median_hold={m.get('median_hold_s', 0):.0f}s, <24h={m.get('intraday_close_share', 0):.2f}",
                    f"{g.hold_median_min_s}-{g.hold_median_max_s}s, >={g.intraday_close_share_min}",
                    g.hold_median_min_s <= m.get("median_hold_s", 0) <= g.hold_median_max_s
                    and m.get("intraday_close_share", 0) >= g.intraday_close_share_min))
    gates.append(_g("G4 not HFT/MM", "D-B1" if "D-B1" in vetoes else "ok", "no D-B1", "D-B1" not in vetoes))
    gates.append(_g("G5 profitability", f"twr_all={m.get('twr_all')}, twr_180={m.get('twr_180d')}, net_all={m.get('net_all', 0):.0f}, net_180={m.get('net_180d', 0):.0f}",
                    "all > 0", (m.get("twr_all") or 0) > 0 and (m.get("twr_180d") or 0) > 0
                    and m.get("net_all", 0) > 0 and m.get("net_180d", 0) > 0))
    best, top5 = m.get("best_month_share"), m.get("top5_share")
    tern = m.get("tercile_net")
    if g.concentration_mode == "robust":
        ex5 = m.get("ex_top5_net_180d")
        bms, t5g = m.get("best_month_pos_share_180d"), m.get("top5_gross_share_all")
        gates.append(_g("G6 consistency",
                        f"pos_months={m.get('positive_months_last6')}, best_month_pos={bms}, top5_gross={t5g}, "
                        f"ex_top5_180d={ex5}, terciles={tern}",
                        f">={g.positive_months_min_of6}/6, <={g.best_month_share_max}, <={g.top5_trades_share_max}, "
                        "ex-top5>0, terciles>0",
                        (m.get("positive_months_last6") or 0) >= g.positive_months_min_of6
                        and bms is not None and bms <= g.best_month_share_max
                        and t5g is not None and t5g <= g.top5_trades_share_max
                        and ex5 is not None and ex5 > 0
                        and (not h.terciles_all_positive or (tern is not None and all(x > 0 for x in tern)))
                        and (m.get("rolling90_positive") or 0) >= h.rolling90_positive_min))
    else:
        gates.append(_g("G6 consistency",
                    f"pos_months={m.get('positive_months_last6')}, best_month={best}, top5={top5}, terciles={tern}",
                    f">={g.positive_months_min_of6}/6, <={g.best_month_share_max}, <={g.top5_trades_share_max}, terciles>0",
                    (m.get("positive_months_last6") or 0) >= g.positive_months_min_of6
                    and best is not None and best <= g.best_month_share_max
                    and top5 is not None and top5 <= g.top5_trades_share_max
                    and (not h.terciles_all_positive or (tern is not None and all(x > 0 for x in tern)))
                    and (m.get("rolling90_positive") or 0) >= h.rolling90_positive_min))
    gates.append(_g("G7 drawdown", f"{m.get('max_dd_twr', 0):.2f}", f"<={g.max_dd_twr}",
                    m.get("max_dd_twr", 1) <= g.max_dd_twr))
    lp = m.get("lev_daily_p95") if m.get("lev_daily_p95") is not None else m.get("lev_p95")
    gates.append(_g("G8 leverage", lp, f"p95<={g.eff_leverage_tw_max}x (account-level daily; margin usage not evaluated)",
                    NOT_EVALUATED if lp is None else lp <= g.eff_leverage_tw_max))
    liq = next((f for f in findings if f.code == "D-R4"), None)
    l180 = liq.metrics["liquidations_180d"] if liq else 0
    ltot = liq.metrics["liquidations_total"] if liq else 0
    gates.append(_g("G9 liquidations", f"180d={l180}, total={ltot}", f"180d<={g.liquidations_window_max}, total<=1",
                    l180 <= g.liquidations_window_max and ltot <= 1))
    gates.append(_g("G10 integrity", vetoes, "no VETO", not vetoes))
    gates.append(_g("G11 statistical edge", f"t={m.get('tstat', 0):.2f}, dsr={m.get('dsr_prob', 0):.3f}",
                    f"t>={g.tstat_min}, dsr>={g.dsr_prob_min}",
                    m.get("tstat", 0) >= g.tstat_min and m.get("dsr_prob", 0) >= g.dsr_prob_min))
    gates.append(_g("G12 size floor", f"{m.get('median_equity', 0):.0f}", f">={g.median_equity_min_usd}",
                    m.get("median_equity", 0) >= g.median_equity_min_usd))
    return gates


def assess(ctx: Ctx, recon_ok: bool = True, history_truncated: bool = False,
           n_trials: int = 5000, extra: list | None = None) -> dict:
    """Full verdict for one wallet: stage, category, gates, findings, metrics."""
    findings = run_all(ctx) + list(extra or [])
    v = verdict(findings)
    cat = classify_algo(ctx)
    base = {"address": ctx.address, "verdict": v, "category": cat, "findings": findings}
    if not recon_ok:
        return {**base, "stage": "reconcile_fail", "gates": [], "metrics": {}, "reasons": ["reconcile"]}
    if history_truncated:
        return {**base, "stage": "history_truncated", "gates": [], "metrics": {},
                "reasons": ["needs archive backfill (P7)"]}
    m = compute_metrics(ctx, n_trials)
    if not m.get("n_trips"):
        return {**base, "stage": "vet_fail", "gates": [], "metrics": m, "reasons": ["no_round_trips"]}
    gates = evaluate_gates(ctx, m, findings, cat)
    g_ = ctx.cfg.gates
    failed = [x["gate"].split()[0] for x in gates if x["pass"] is False]
    vetoes = v["vetoes"]
    if "D-B1" in vetoes:
        cat = {**cat, "category": "MM_HFT"}
    fgi = m.get("first_genuine_idx")
    reformed = (m.get("genuine_coverage", 0) > 0 and fgi is not None
                and fgi > ctx.cfg.history.genuine_start_max_month - 1
                and m.get("genuine_months", 0) >= 3 and not vetoes
                and m.get("track_days", 0) >= ctx.cfg.gates.min_track_days)
    t = ctx.cfg.tiers
    soft = {"G11", "G6", "G7", "G2"}
    provisional = (
        t.provisional and not vetoes and failed and set(failed) <= soft
        and ("G7" not in failed or m.get("max_dd_twr", 1) <= g_.max_dd_twr + t.dd_slack)
        and ("G2" not in failed or (m.get("weekly_coverage", 0) >= t.weekly_coverage_min
                                    and (m.get("max_gap_days") or 999) <= t.max_gap_days))
        and ("G6" not in failed or (m.get("ex_top5_net_180d") or 0) > 0))
    if provisional:
        stage = "provisional"
    elif failed or vetoes:
        stage = "reformed" if reformed and set(failed) <= {"G1b"} else "vet_fail"
    elif v["needs_qa"]:
        stage = "needs_qa"
    else:
        stage = "qualified"
    return {**base, "category": cat, "stage": stage, "gates": gates, "metrics": m,
            "reasons": sorted(set(failed + vetoes))}


COMPONENTS = {"tenure": 20, "edge": 20, "consistency": 20, "discipline": 15,
              "efficiency": 10, "regularity": 8, "alpha": 7}


def _pct(vals: list[float]) -> list[float]:
    """Percentile rank in [0,1] with ties sharing their average rank; a lone entry ranks 1.0."""
    n = len(vals)
    if n == 1:
        return [1.0]
    out = []
    for v in vals:
        below = sum(1 for x in vals if x < v)
        equal = sum(1 for x in vals if x == v)
        out.append((below + (equal - 1) / 2) / (n - 1))
    return out


def rank_qualified(results: list[dict], weights: dict | None = None, flag_penalty: float = 5) -> list[dict]:
    """Composite score within each category (MDT/ADT/UNSURE ranked separately)."""
    w = weights or COMPONENTS
    import math

    q = [r for r in results if r["stage"] in ("qualified", "provisional")]
    for tier, cat in {(r["stage"], r["category"]["category"]) for r in q}:
        grp = [r for r in q if r["stage"] == tier and r["category"]["category"] == cat]
        feats = {
            "tenure": [math.log1p(r["metrics"]["genuine_months"]) for r in grp],
            "edge": [(r["metrics"]["dsr_prob"] + min(r["metrics"]["tstat"], 6) / 6
                      + min(r["metrics"]["sortino"], 8) / 8) for r in grp],
            "consistency": [(r["metrics"].get("positive_months_last6") or 0)
                            - (r["metrics"].get("best_month_share") or 1)
                            + (r["metrics"].get("rolling90_positive") or 0) for r in grp],
            "discipline": [-(r["metrics"]["max_dd_twr"]) - (r["metrics"].get("lev_p95") or 0) / 10 for r in grp],
            "efficiency": [(r["metrics"].get("profit_factor") or 0) + r["metrics"].get("expectancy_bps", 0) / 100
                           for r in grp],
            "regularity": [r["metrics"]["weekly_coverage"] for r in grp],
            "alpha": [r["metrics"].get("sharpe", 0) for r in grp],
        }
        pct = {k: _pct(v) for k, v in feats.items()}
        for i, r in enumerate(grp):
            s = sum(w[k] * pct[k][i] for k in w)
            s -= min(15, flag_penalty * len(r["verdict"]["flags"]))
            r["score"] = round(s, 2)
        grp.sort(key=lambda r: (-r["score"], -r["metrics"]["genuine_months"]))
        for rank, r in enumerate(grp, 1):
            r["rank"] = rank
    return results
