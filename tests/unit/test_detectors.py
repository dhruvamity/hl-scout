
from hlscout.detectors import automation as A
from hlscout.detectors import flows as F
from hlscout.detectors import risk as R
from hlscout.detectors import run_all, verdict
from tests.helpers import DAY, HOUR, Wallet, clean_wallet


def codes(ctx, sev=None):
    return {f.code for f in run_all(ctx) if sev is None or f.severity == sev}


def test_clean_trader_has_no_veto():
    ctx = clean_wallet().ctx()
    v = verdict(run_all(ctx))
    assert v["vetoes"] == [], v


def test_martingale_vetoed():
    w = Wallet()
    w.equity(w.t0 - HOUR, 100_000, 0)
    for k in range(10):
        t = w.t0 + k * DAY
        w.fill(t, "SOL", "B", 1, 100)
        w.fill(t + 60_000, "SOL", "B", 2, 90)
        w.fill(t + 120_000, "SOL", "B", 4, 80)
        w.fill(t + 3 * HOUR, "SOL", "A", 7, 95, pnl=5)
    w.equity(w.t0 + 11 * DAY, 100_100, 100)
    f = R.d_r1_martingale(w.ctx())
    assert f.severity == "VETO" and f.metrics["martingale_freq"] == 1.0


def _rescue_wallet(n_events):
    w = Wallet()
    w.equity(w.t0 - HOUR, 1000, 0)
    w.fill(w.t0, "BTC", "B", 10, 100)  # $1000 notional on $1000 equity
    for k in range(n_events):
        t = w.t0 + (k + 1) * 10 * DAY
        w.equity(t - HOUR, 1000, 0)
        w.deposit(t, 500)
    w.equity(w.t0 + 40 * DAY, 1000, 0)
    return w


def test_rescue_deposit_flag_then_veto():
    marks = lambda coin, t: 60.0
    one = _rescue_wallet(1).ctx(marks=marks)
    assert F.d_m2_rescue_deposit(one).severity == "FLAG"
    two = _rescue_wallet(2).ctx(marks=marks)
    assert F.d_m2_rescue_deposit(two).severity == "VETO"
    # position was cut around the deposit -> not a rescue
    w = _rescue_wallet(1)
    w.fill(w.t0 + 10 * DAY + 5 * 60_000, "BTC", "A", 5, 60, pnl=-200)
    assert F.d_m2_rescue_deposit(w.ctx(marks=marks)) is None


def test_deposit_inflation_flag():
    w = Wallet()
    w.deposit(w.t0 + 30 * DAY, 20_000)
    w.equity(w.t0, 1000, 0)
    w.equity(w.t0 + 29 * DAY, 1000, 0)
    w.equity(w.t0 + 31 * DAY, 21_000, 0)
    w.fill(w.t0, "BTC", "B", 1, 100)
    f = F.d_m1_deposit_inflation(w.ctx())
    assert f.severity == "VETO" and f.metrics["flow_share"] > 0.9  # naive ROI +2000%, TWR 0
    assert abs(f.metrics["twr"]) < 1e-6  # deposits alone never move TWR


def test_hft_mm_vetoed():
    w = Wallet()
    w.equity(w.t0, 50_000, 0)
    for k in range(400):
        w.fill(w.t0 + k * 1000, "BTC", "B" if k % 2 == 0 else "A", 1, 100, crossed=False)
    f = A.d_b1_hft_mm(w.ctx())
    assert f.severity == "VETO" and set(f.evidence[0]["reasons"]) >= {"maker_share", "avg_hold"}


def test_liquidation_vetoed_and_single_old_one_flagged():
    w = clean_wallet()
    w.fill(w.t0 + 100 * DAY, "ETH", "B", 1, 100)
    w.fill(w.t0 + 100 * DAY + HOUR, "ETH", "A", 1, 50, pnl=-50, dir_="Liquidated Cross Long")
    ctx = w.ctx(now_ms=w.t0 + 120 * DAY)
    assert R.d_r4_liquidations(ctx).severity == "VETO"  # inside last 180d


def test_leverage_spike():
    w = Wallet()
    w.equity(w.t0 - HOUR, 1000, 0)
    for k in range(30):
        t = w.t0 + k * DAY
        w.equity(t - HOUR, 1000, 0)
        w.trip(t, sz=40.0, px=100.0, exit_px=100.5)  # $4000 on $1000 = 4x ... first 5 lower
    for k in range(30, 40):
        t = w.t0 + k * DAY
        w.equity(t - HOUR, 1000, 0)
        w.trip(t, sz=400.0, px=100.0, exit_px=100.5)  # 40x
    f = R.d_r5_leverage_spikes(w.ctx())
    assert f.severity == "VETO" and f.metrics["lev_max"] >= 39


def test_blacklist_and_vault_role():
    w = clean_wallet()
    ctx = w.ctx(role={"role": "vault"})
    assert A.d_b3_vault_protocol(ctx).severity == "VETO"
    ctx.address = "0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00"
    assert A.d_b5_blacklist(ctx).severity == "VETO"


def test_board_vs_account():
    w = clean_wallet()
    ctx = w.ctx(lb={"pnl_month": 5000.0}, month_pnl=[[1, "100"], [2, "90"]])
    from hlscout.detectors import optics
    assert optics.d_c1_board_vs_account(ctx).severity == "VETO"


def test_manual_vs_algo_classifier():
    bot = Wallet()
    for k in range(600):  # 24/7, every 500 ms, identical size
        bot.fill(bot.t0 + k * 7_200_000 // 5, "BTC", "B" if k % 2 == 0 else "A", 1.0, 100)
    bot.equity(bot.t0, 10_000, 0)
    human = clean_wallet(n_trips=200)
    assert A.classify_algo(bot.ctx())["p_algo"] > 0.7
    assert A.classify_algo(human.ctx())["p_algo"] < 0.3
