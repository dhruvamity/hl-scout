import polars as pl

from hlscout.archive.hypedexer import derive_closed_pnl, fetch_fills, norm_archive_fill
from hlscout.ingest.hydrate import FILL_SCHEMA


class Fake:
    def __init__(self):
        self.calls = []

    async def get(self, url, params):
        self.calls.append(params)
        if "cursor" not in params:
            return {"data": [{"user": "x", "coin": "BTC", "px": "100", "sz": "1", "side": "B",
                              "time": "2025-01-01T00:00:00Z", "tid": 1}],
                    "next_cursor": "c1", "has_more": True}
        return {"data": [{"user": "x", "coin": "BTC", "px": "110", "sz": "1", "side": "S",
                          "time": 1735693200000, "tid": 2}], "next_cursor": None, "has_more": False}


async def test_paging_and_normalise():
    g = Fake()
    rows = await fetch_fills(g, "0xabc", 0, 2_000_000_000_000)
    assert [r["tid"] for r in rows] == [1, 2] and g.calls[1]["cursor"] == "c1"
    assert rows[0]["side"] == "B" and rows[1]["side"] == "A"


def test_derive_pnl_and_start_position():
    rows = [norm_archive_fill(r) for r in [
        {"coin": "BTC", "px": 100, "sz": 2, "side": "B", "time": 1, "tid": 1},
        {"coin": "BTC", "px": 110, "sz": 1, "side": "S", "time": 2, "tid": 2},
        {"coin": "BTC", "px": 90, "sz": 3, "side": "S", "time": 3, "tid": 3}]]
    df = derive_closed_pnl(pl.DataFrame(rows, schema=FILL_SCHEMA))
    assert df["closed_pnl"].to_list() == [0.0, 10.0, -10.0]  # flip: only 1 unit closes at 100->90
    assert df["start_position"].to_list() == [0.0, 2.0, 1.0]


def test_coarse_months_count_toward_tenure_only_when_enabled():
    from hlscout.scoring.consistency import _trip_frame, grade_months
    from tests.helpers import DAY, Wallet

    w = Wallet(t0=1_700_000_000_000)
    for k in range(30):  # fills only start 4 months after the portfolio history does
        w.trip(w.t0 + 120 * DAY + k * 3 * DAY, "BTC", "B", 5.0, 100.0, 101.0)
    w.deposit(w.t0 - 3600_000, 10_000)
    for d in range(0, 120, 5):
        w.equity(w.t0 + d * DAY, 10_000 + d, d)
    w.equity(w.t0 + 300 * DAY, 11_000, 1000)
    ctx = w.ctx()
    assert "coarse" not in grade_months(ctx, _trip_frame(ctx))["grade"].to_list()
    ctx.coarse_ok = True
    g = grade_months(ctx, _trip_frame(ctx))["grade"].to_list()
    assert g.count("coarse") >= 3


async def test_backfill_merges_and_clears_truncation(tmp_path):
    import json

    from hlscout.archive.backfill import backfill_address
    from hlscout.ingest.hydrate import LEDGER_SCHEMA, raw_path

    addr = "0x" + "1" * 40
    have = pl.DataFrame([{"time": 5_000_000, "coin": "BTC", "px": 100.0, "sz": 1.0, "side": "A", "dir": "",
                          "start_position": 1.0, "closed_pnl": 3.0, "fee": 0.0, "crossed": True, "oid": 9,
                          "tid": 9, "twap_id": None, "fee_token": "USDC", "liquidation": None,
                          "hash": "h"}], schema=FILL_SCHEMA)
    for kind, df in (("fills", have), ("ledger", pl.DataFrame(
            [{"time": 1_000_000, "hash": "x", "type": "deposit", "usdc": 1.0, "user": None,
              "destination": None, "token": None, "amount": None, "to_perp": None, "fee": None,
              "raw_json": "{}"}], schema=LEDGER_SCHEMA))):
        p = raw_path(tmp_path, kind, addr)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(p)
    pp = raw_path(tmp_path, "portfolio", addr).with_suffix(".json")
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps({}))

    class G:
        async def get(self, url, params):
            return {"data": [{"coin": "BTC", "px": 90, "sz": 1, "side": "B", "time": 2_000_000, "tid": 1}],
                    "has_more": False}

    out = await backfill_address(G(), tmp_path, addr)
    df = pl.read_parquet(raw_path(tmp_path, "fills", addr))
    assert out["fetched"] == 1 and df.height == 2 and df["time"].min() == 2_000_000
    assert df.sort("time")["closed_pnl"].to_list() == [0.0, 3.0]
