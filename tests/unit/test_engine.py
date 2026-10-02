import numpy as np

from hlscout.scoring.dsr import deflated_sharpe_prob, tstat
from hlscout.scoring.engine import assess, rank_qualified
from tests.helpers import DAY, HOUR, clean_wallet


def test_dsr_and_tstat():
    rng = np.random.default_rng(0)
    good = rng.normal(0.01, 0.01, 250)
    noise = rng.normal(0.0, 0.01, 250)
    assert tstat(good) > 10 and deflated_sharpe_prob(good, 5000) > 0.99
    assert deflated_sharpe_prob(noise, 5000) < 0.5


def test_clean_wallet_assessed(monkeypatch):
    ctx = clean_wallet(n_trips=200, days=260).ctx()
    r = assess(ctx)
    assert r["stage"] == "qualified", (r["stage"], r["reasons"])
    assert r["category"]["category"] in {"MDT", "UNSURE"}


def test_short_history_fails_g1():
    ctx = clean_wallet(n_trips=40, days=60).ctx()
    r = assess(ctx)
    assert r["stage"] == "vet_fail" and "G1" in r["reasons"]


def test_reconcile_fail_and_truncated_not_scored():
    ctx = clean_wallet().ctx()
    assert assess(ctx, recon_ok=False)["stage"] == "reconcile_fail"
    assert assess(ctx, history_truncated=True)["stage"] == "history_truncated"


def test_late_clean_wallet_is_reformed():
    """Violations early (liquidation months), clean only recently -> reformed, never qualified."""
    w = clean_wallet(n_trips=200, days=300, seed=3)
    for k in range(4):  # liquidations in the first 4 months
        t = w.t0 + (k * 30 + 5) * DAY
        w.fill(t, "ETH", "B", 1, 100)
        w.fill(t + HOUR, "ETH", "A", 1, 50, pnl=-50, dir_="Liquidated Cross Long")
    r = assess(w.ctx())
    assert r["stage"] != "qualified"


def test_ranking_within_category():
    a = {"stage": "qualified", "category": {"category": "MDT"}, "verdict": {"flags": []},
         "metrics": {"genuine_months": 12, "dsr_prob": 0.99, "tstat": 4, "sortino": 5, "max_dd_twr": 0.1,
                     "weekly_coverage": 0.9, "sharpe": 2, "profit_factor": 2}}
    b = {**a, "metrics": {**a["metrics"], "genuine_months": 6, "dsr_prob": 0.92, "tstat": 2.1}}
    c = {**a, "category": {"category": "ADT"}}
    rank_qualified([a, b, c])
    assert a["rank"] == 1 and b["rank"] == 2 and c["rank"] == 1 and a["score"] > b["score"]


def test_report_lists_closest_misses():
    from hlscout.reports.daily import render

    def res(addr, failed, vetoes, t):
        return {"address": addr, "stage": "vet_fail", "category": {"category": "MDT", "p_algo": 0.1},
                "gates": [{"gate": g, "pass": False, "value": 0, "threshold": 0} for g in failed],
                "verdict": {"vetoes": vetoes, "flags": []}, "reasons": failed + vetoes,
                "metrics": {"tstat": t, "dsr_prob": 0.5, "net_180d": 1000, "genuine_months": 3}}

    md = render([res("0xnear", ["G10", "G1b"], ["D-R1"], 5.0), res("0xfar", ["G2", "G3", "G6"], [], 1.0)])
    assert md.index("0xnear") < md.index("0xfar") and "Closest misses" in md


def test_provisional_when_only_statistical_gate_fails():
    ctx = clean_wallet(n_trips=200, days=260).ctx()
    r = assess(ctx, n_trials=10**12)  # absurd multiple-testing correction: DSR can't pass, everything else does
    assert r["stage"] == "provisional", (r["stage"], r["reasons"])
    assert r["reasons"] == ["G11"]
    ctx2 = clean_wallet(n_trips=200, days=260).ctx()
    ctx2.cfg.tiers.provisional = False
    assert assess(ctx2, n_trials=10**12)["stage"] == "vet_fail"


def test_robust_concentration_does_not_veto_a_broad_edge():
    ctx = clean_wallet(n_trips=200, days=260).ctx()
    ctx.cfg.gates.concentration_mode = "robust"
    r = assess(ctx)
    assert r["stage"] == "qualified", (r["stage"], r["reasons"])
    assert r["metrics"]["ex_top5_net_all"] > 0


def test_robust_concentration_vetoes_a_lottery():
    from hlscout.detectors.optics import d_c2_concentration
    from tests.helpers import Wallet

    w = Wallet()
    w.deposit(w.t0 - HOUR, 10_000)
    w.equity(w.t0 - HOUR, 10_000, 0)
    for k in range(30):
        w.trip(w.t0 + k * 5 * DAY, "BTC", "B", 1.0, 100.0, 99.9)        # steady tiny losers
    w.trip(w.t0 + 200 * DAY, "BTC", "B", 100.0, 100.0, 140.0)             # one giant win is the whole record
    ctx = w.ctx()
    ctx.cfg.gates.concentration_mode = "robust"
    f = d_c2_concentration(ctx)
    assert f is not None and f.severity == "VETO" and f.evidence[0]["breached"] == ["lottery"]
