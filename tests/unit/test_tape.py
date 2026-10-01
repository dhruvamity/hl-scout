import json
from datetime import UTC, datetime

import polars as pl

from hlscout.ingest.tape import (
    TapeRecorder,
    TradeBuffer,
    compact_day,
    parse_trade,
    prune_raw,
)
from hlscout.storage import connect_state

A, B, C = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40
T0 = int(datetime(2026, 9, 1, 10, 30, tzinfo=UTC).timestamp() * 1000)


def tr(tid, t, buyer, seller, side="B", coin="BTC", px="100", sz="2"):
    return {"coin": coin, "side": side, "px": px, "sz": sz, "hash": "0x1", "time": t,
            "tid": tid, "users": [buyer, seller]}


def test_parse_rejects_missing_users():
    assert parse_trade({**tr(1, T0, A, B), "users": []}) is None
    assert parse_trade(tr(1, T0, A.upper(), B))["buyer"] == A


def test_dedupe_and_hour_partition(tmp_path):
    buf = TradeBuffer(tmp_path / "tape")
    assert buf.add(parse_trade(tr(1, T0, A, B)))
    assert not buf.add(parse_trade(tr(1, T0, A, B)))  # duplicate tid
    buf.add(parse_trade(tr(2, T0 + 3_600_000, A, B)))  # next hour
    assert buf.flush() == 2
    files = sorted((tmp_path / "tape").rglob("*.parquet"))
    assert [f.parent.name for f in files] == ["hour=10", "hour=11"]
    assert not list((tmp_path / "tape").rglob("*.tmp"))


def test_recorder_handles_messages(tmp_path):
    st = connect_state(tmp_path)
    buf = TradeBuffer(tmp_path / "tape")
    rec = TapeRecorder(buf, st, None, None)
    msg = json.dumps({"channel": "trades", "data": [tr(1, T0, A, B), tr(2, T0 + 1, A, C)]})
    assert rec.handle_message(msg) == 2
    assert rec.handle_message(msg) == 0
    assert rec.handle_message(json.dumps({"channel": "pong"})) == 0
    rec.record_gap(1, 2, "test")
    assert st.execute("SELECT count(*) FROM tape_gaps").fetchone()[0] == 1


def test_compaction_stats(tmp_path):
    buf = TradeBuffer(tmp_path / "tape")
    # A buys from B twice (A taker), then A sells to C once (A taker: side 'A' means seller took)
    for row in [tr(1, T0, A, B, "B"), tr(2, T0 + 10_000, A, B, "B"), tr(3, T0 + 20_000, C, A, "A")]:
        buf.add(parse_trade(row))
    buf.flush()
    out = compact_day(tmp_path / "tape", tmp_path / "stats", "2026-09-01")
    df = pl.read_parquet(out).filter(pl.col("address") == A).row(0, named=True)
    assert df["trades"] == 3 and df["buys"] == 2 and df["sells"] == 1
    assert df["notional"] == 600 and df["median_gap_s"] == 10.0
    assert df["maker_share_proxy"] == 0.0 and df["top_counterparties"][0] == B
    b = pl.read_parquet(out).filter(pl.col("address") == B).row(0, named=True)
    assert b["maker_share_proxy"] == 1.0


def test_prune(tmp_path):
    buf = TradeBuffer(tmp_path / "tape")
    buf.add(parse_trade(tr(1, T0, A, B)))
    buf.flush()
    assert prune_raw(tmp_path / "tape", 120, datetime(2026, 9, 10, tzinfo=UTC)) == []
    assert prune_raw(tmp_path / "tape", 120, datetime(2027, 3, 1, tzinfo=UTC)) == ["date=2026-09-01"]


def test_preload_dedupes_across_restart(tmp_path):
    b1 = TradeBuffer(tmp_path / "tape")
    b1.add(parse_trade(tr(1, T0, A, B)))
    b1.flush()
    b2 = TradeBuffer(tmp_path / "tape")
    assert b2.preload() == 1
    assert not b2.add(parse_trade(tr(1, T0, A, B)))
