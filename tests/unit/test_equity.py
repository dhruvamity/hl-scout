import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from hlscout.ingest.hydrate import FILL_SCHEMA
from hlscout.recon.equity import FLOW_SCHEMA, equity_series, flow_events, reconcile, twr_curve

DAY = 86_400_000
T0 = 1_700_000_000_000


def portfolio(points):
    return {"perpAllTime": {"accountValueHistory": [[t, str(e)] for t, e, _ in points],
                            "pnlHistory": [[t, str(p)] for t, _, p in points]}}


def fill(t, pnl, fee=0.0):
    return {"time": t, "coin": "BTC", "px": 100.0, "sz": 1.0, "side": "A", "dir": "", "start_position": 1.0,
            "closed_pnl": pnl, "fee": fee, "crossed": True, "oid": t, "tid": t, "twap_id": None,
            "fee_token": "USDC", "liquidation": None, "hash": "h"}


EMPTY_FUND = pl.DataFrame(schema={"time": pl.Int64, "coin": pl.Utf8, "usdc": pl.Float64, "szi": pl.Float64,
                                  "funding_rate": pl.Float64})


def test_reconcile_ok_when_fills_explain_platform_pnl():
    f = pl.DataFrame([fill(T0 + DAY, 80.0, 1.0), fill(T0 + 2 * DAY, 30.0, 1.0)], schema=FILL_SCHEMA)
    pf = portfolio([(T0, 1000, 0), (T0 + 3 * DAY, 1108, 108)])
    r = reconcile(f, EMPTY_FUND, pf, capital=1000)
    assert r["ok"] and abs(r["ours"] - 108) < 1e-9


def test_reconcile_fails_when_pnl_is_missing():
    f = pl.DataFrame([fill(T0 + DAY, 80.0)], schema=FILL_SCHEMA)  # platform saw +500, we only explain +80
    pf = portfolio([(T0, 1000, 0), (T0 + 3 * DAY, 1500, 500)])
    r = reconcile(f, EMPTY_FUND, pf, capital=1000)
    assert not r["ok"] and r["residual_pct"] < -20


def test_reconcile_counts_unrealised_pnl():
    f = pl.DataFrame([fill(T0 + DAY, 10.0)], schema=FILL_SCHEMA)
    pf = portfolio([(T0, 1000, 0), (T0 + 3 * DAY, 1060, 60)])
    assert not reconcile(f, EMPTY_FUND, pf, capital=1000)["ok"]
    assert reconcile(f, EMPTY_FUND, pf, capital=1000, unrealized=50.0)["ok"]


@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(min_value=-500, max_value=5000, allow_nan=False), min_size=1, max_size=15))
def test_property_flows_alone_never_move_twr(flows):
    pts, e = [(T0, 1000.0, 0.0)], 1000.0
    fl = []
    for i, x in enumerate(flows, 1):
        e = max(e + x, 1000.0) if x < 0 else e + x
        applied = e - pts[-1][1]
        fl.append({"time": T0 + i * DAY - 1, "flow": applied, "kind": "deposit"})
        pts.append((T0 + i * DAY, e, 0.0))  # platform PnL stays 0: only deposits/withdrawals moved equity
    curve = twr_curve(equity_series(portfolio(pts)), pl.DataFrame(fl, schema=FLOW_SCHEMA))
    assert abs(float(curve["twr_index"][-1]) - 1.0) < 1e-9


def test_flow_events_classification():
    led = pl.DataFrame([
        {"time": 1, "hash": "a", "type": "deposit", "usdc": 100.0, "user": None, "destination": None,
         "token": None, "amount": None, "to_perp": None, "fee": None, "raw_json": "{}"},
        {"time": 2, "hash": "b", "type": "withdraw", "usdc": 40.0, "user": None, "destination": None,
         "token": None, "amount": None, "to_perp": None, "fee": 1.0, "raw_json": "{}"},
        {"time": 3, "hash": "c", "type": "rewardsClaim", "usdc": 5.0, "user": None, "destination": None,
         "token": None, "amount": None, "to_perp": None, "fee": None, "raw_json": '{"usdc": 5.0}'},
    ], schema={"time": pl.Int64, "hash": pl.Utf8, "type": pl.Utf8, "usdc": pl.Float64, "user": pl.Utf8,
               "destination": pl.Utf8, "token": pl.Utf8, "amount": pl.Float64, "to_perp": pl.Boolean,
               "fee": pl.Float64, "raw_json": pl.Utf8})
    out = flow_events(led, "0x" + "a" * 40)
    assert out["flow"].to_list() == [100.0, -41.0, 5.0]
