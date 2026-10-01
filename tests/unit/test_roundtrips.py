import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from hlscout.ingest.hydrate import FILL_SCHEMA
from hlscout.recon.roundtrips import build_round_trips


def mk(rows):
    out, pos = [], {}
    for i, (t, coin, side, sz, px, pnl) in enumerate(rows):
        sp = pos.get(coin, 0.0)
        out.append({"time": t, "coin": coin, "px": px, "sz": sz, "side": side, "dir": "",
                    "start_position": sp, "closed_pnl": pnl, "fee": 0.1, "crossed": True,
                    "oid": i, "tid": i, "twap_id": None, "fee_token": "USDC", "liquidation": None,
                    "hash": "h"})
        pos[coin] = sp + (sz if side == "B" else -sz)
    return pl.DataFrame(out, schema=FILL_SCHEMA)


def test_simple_long():
    df, broken = build_round_trips(mk([(1, "BTC", "B", 1, 100, 0), (5, "BTC", "A", 1, 110, 10)]))
    r = df.row(0, named=True)
    assert df.height == 1 and not broken
    assert r["side"] == "long" and r["pnl"] == 10 and r["vwap_in"] == 100 and r["vwap_out"] == 110
    assert abs(r["fees"] - 0.2) < 1e-9


def test_flip_splits_fill():
    df, _ = build_round_trips(mk([(1, "ETH", "B", 2, 100, 0), (2, "ETH", "A", 5, 90, -20),
                                  (3, "ETH", "B", 3, 95, 15)]))
    assert df.height == 2
    assert df["side"].to_list() == ["long", "short"]
    assert abs(df["fees"].sum() - 0.3) < 1e-9 and abs(df["pnl"].sum() - (-5)) < 1e-9


def test_martingale_underwater_adds():
    df, _ = build_round_trips(mk([(1, "SOL", "B", 1, 100, 0), (60_000, "SOL", "B", 2, 90, 0),
                                  (120_000, "SOL", "B", 4, 80, 0), (180_000, "SOL", "A", 7, 95, 5)]))
    r = df.row(0, named=True)
    assert r["adds"] == 2 and r["underwater_add_share"] == 1.0 and r["max_size"] == 7
    assert r["first_clip"] == 1


def test_continuity_break_flagged():
    fills = mk([(1, "BTC", "B", 1, 100, 0), (2, "BTC", "A", 1, 100, 0)])
    fills = fills.with_columns(
        pl.when(pl.col("time") == 2).then(5.0).otherwise(pl.col("start_position"))
        .alias("start_position"))
    _, broken = build_round_trips(fills)
    assert broken == {"BTC"}


def test_liquidation_and_funding():
    f = mk([(1, "BTC", "B", 1, 100, 0), (10, "BTC", "A", 1, 50, -50)]).with_columns(
        pl.when(pl.col("time") == 10).then(pl.lit("Liquidated Cross Long"))
        .otherwise(pl.col("dir")).alias("dir"))
    fund = pl.DataFrame({"time": [5, 20], "coin": ["BTC", "BTC"], "usdc": [-1.5, -9.0],
                         "szi": [1.0, 0.0], "funding_rate": [0.0, 0.0]})
    df, _ = build_round_trips(f, fund)
    assert df["liquidated"][0] and df["funding"][0] == -1.5


@settings(max_examples=100, deadline=None)
@given(st.lists(st.tuples(st.sampled_from("BA"), st.integers(1, 20)), min_size=1, max_size=40))
def test_property_position_continuity(ops):
    rows = [(i + 1, "X", s, float(q), 100.0, 0.0) for i, (s, q) in enumerate(ops)]
    df, broken = build_round_trips(mk(rows))
    assert not broken
    pos = sum(q if s == "B" else -q for s, q in ops)
    for r in df.iter_rows(named=True):
        assert r["close_ts"] >= r["open_ts"] and r["max_size"] > 0
    if pos == 0:
        assert df.height >= 1


def test_same_millisecond_fills_follow_start_position_chain():
    # three partial fills share a timestamp; tids are NOT in execution order
    f = mk([(1, "BTC", "B", 1, 100, 0), (2, "BTC", "A", 0.4, 110, 4), (2, "BTC", "A", 0.6, 111, 6)])
    f = f.with_columns(pl.Series("tid", [10, 30, 20]))  # second partial now has the larger tid
    df, broken = build_round_trips(f)
    assert not broken and df.height == 1 and abs(df["pnl"][0] - 10) < 1e-9


def test_partial_fills_of_opening_order_are_one_clip_not_adds():
    rows = [(1000, "SOL", "B", 0.1, 100, 0), (1500, "SOL", "B", 9.9, 99, 0),   # one ladder fill burst
            (9_000_000, "SOL", "A", 10, 105, 40)]
    df, _ = build_round_trips(mk(rows))
    r = df.row(0, named=True)
    assert r["adds"] == 0 and abs(r["first_clip"] - 10.0) < 1e-9
