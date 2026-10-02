import polars as pl

from hlscout.ingest.hydrate import FILL_SCHEMA
from hlscout.recon.daily import DAY_MS, build_daily, platform_anchors
from hlscout.recon.equity import FLOW_SCHEMA
from hlscout.recon.positions import build_timeline

T0 = 1_700_000_000_000 // DAY_MS * DAY_MS


def fills(rows):
    out = []
    for i, (t, side, sz, px, pnl) in enumerate(rows):
        out.append({"time": t, "coin": "BTC", "px": px, "sz": sz, "side": side, "dir": "", "start_position": None,
                    "closed_pnl": pnl, "fee": 0.0, "crossed": True, "oid": i, "tid": i, "twap_id": None,
                    "fee_token": "USDC", "liquidation": None, "hash": "h"})
    return pl.DataFrame(out, schema=FILL_SCHEMA)


def empty_funding():
    return pl.DataFrame(schema={"time": pl.Int64, "coin": pl.Utf8, "usdc": pl.Float64, "szi": pl.Float64,
                                "funding_rate": pl.Float64})


def test_deposit_only_gives_zero_twr_and_flat_equity():
    f = fills([(T0 + 1000, "B", 1, 100, 0.0), (T0 + 2000, "A", 1, 100, 0.0)])
    flows = pl.DataFrame([{"time": T0 + 3 * DAY_MS + 5, "flow": 5000.0, "kind": "deposit"}], schema=FLOW_SCHEMA)
    pf = {"perpAllTime": {"accountValueHistory": [[T0, "1000"]], "pnlHistory": [[T0, "0"]]}}
    d = build_daily(f, empty_funding(), flows, pf, build_timeline(f), None, T0 + 6 * DAY_MS)
    assert abs(d["twr_index"][-1] - 1) < 1e-9 and d["flow"].sum() == 5000.0
    assert abs(d["equity"][-1] - 6000.0) < 1e-6


def test_unrealised_drawdown_visible_at_daily_resolution():
    # long 10 BTC @100; price path 100 -> 90 -> 100: the dip is a real 10% DD the sparse portfolio hides
    f = fills([(T0 + 1000, "B", 10, 100, 0.0)])
    px = {0: 100.0, 1: 90.0, 2: 100.0, 3: 100.0}
    mark = lambda coin, t: px.get((t - T0) // DAY_MS)  # noqa: E731
    pf = {"perpAllTime": {"accountValueHistory": [[T0, "1000"]], "pnlHistory": [[T0, "0"]]}}
    d = build_daily(f, empty_funding(), pl.DataFrame(schema=FLOW_SCHEMA), pf, build_timeline(f), mark,
                    T0 + 3 * DAY_MS + 10)
    assert d["dd"].max() > 0.09 and abs(d["twr_index"][-1] - 1) < 1e-9 and d["marked"].all()


def test_reanchors_to_platform_equity_and_records_residual():
    f = fills([(T0 + 1000, "B", 1, 100, 0.0), (T0 + DAY_MS + 5, "A", 1, 110, 10.0)])
    pf = {"perpAllTime": {"accountValueHistory": [[T0, "1000"], [T0 + 2 * DAY_MS - 1, "1050"]],
                          "pnlHistory": [[T0, "0"], [T0 + 2 * DAY_MS - 1, "50"]]}}
    d = build_daily(f, empty_funding(), pl.DataFrame(schema=FLOW_SCHEMA), pf, build_timeline(f), None,
                    T0 + 2 * DAY_MS)
    assert abs(d.filter(pl.col("time") == T0 + 2 * DAY_MS - 1)["equity"][0] - 1050) < 1e-9
    assert abs(d["resid"].abs().max() - 40) < 1e-6  # we saw +10, platform says +50


def test_anchor_merge_prefers_finest_window():
    pf = {"perpAllTime": {"accountValueHistory": [[100, "1"], [200, "2"]]},
          "perpMonth": {"accountValueHistory": [[200, "2.5"], [250, "3"]]}}
    assert platform_anchors(pf) == [(100, 1.0), (200, 2.5), (250, 3.0)]
