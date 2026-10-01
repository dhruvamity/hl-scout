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
