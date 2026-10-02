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


async def test_credit_budget_stops_fetch():
    import sqlite3

    import pytest

    from hlscout.archive.hypedexer import CreditBudget, OutOfCredits, call_credits

    assert call_credits(0) == 1 and call_credits(25) == 2 and call_credits(1000) == 41
    con = sqlite3.connect(":memory:", isolation_level=None)
    tight = CreditBudget(con, monthly=40)  # a full 1000-row page (41 credits) cannot be afforded
    with pytest.raises(OutOfCredits):
        await fetch_fills(Fake(), "0xabc", 0, 2_000_000_000_000, limit=1000, budget=tight)
    ok = CreditBudget(con, monthly=500)
    rows = await fetch_fills(Fake(), "0xabc", 0, 2_000_000_000_000, limit=1000, budget=ok)
    assert len(rows) == 2 and ok.used() == 4  # two pages of one row: 2 credits each


def test_partial_history_with_180d_cover_is_not_truncated():
    import polars as pl

    from hlscout.ingest.hydrate import FILL_SCHEMA
    from hlscout.recon.vet import audit
    from tests.helpers import DAY, Wallet

    w = Wallet(t0=1_700_000_000_000)
    w.deposit(w.t0 - 400 * DAY, 10_000)          # account is older than the fills we hold
    for i in range(9600):                         # ~10k fills, all within the last 200 days
        w.fill(w.t0 + 200 * DAY + i * 1_000_000, "BTC", "B" if i % 2 == 0 else "A", 1.0, 100.0)
    w.equity(w.t0 - 400 * DAY, 10_000, 0)
    w.equity(w.t0 + 399 * DAY, 10_500, 500)
    ctx = w.ctx()
    raw = {"fills": pl.DataFrame(w.fills, schema=FILL_SCHEMA), "funding": ctx.funding, "ledger": ctx.ledger,
           "portfolio": ctx.portfolio, "meta": {}, "now_ms": w.t0 + 399 * DAY}
    a = audit("0x" + "a" * 40, raw)
    assert a["partial_history"] and not a["history_truncated"]
    raw["now_ms"] = w.t0 + 250 * DAY             # only 50 days of fills: still truncated
    assert audit("0x" + "a" * 40, raw)["history_truncated"]


def test_naive_iso_time_is_utc_and_spot_dropped():
    r = norm_archive_fill({"coin": "BTC", "px": 1, "sz": 1, "side": "B", "time": "2026-02-12T08:24:51.273000",
                           "tid": 1, "isLiquidation": 1, "liquidatedUser": "0xother", "user": "0xme"})
    assert r["time"] == 1770884691273  # 2026-02-12 08:24:51.273 UTC
    assert r["liquidation"] is None    # we were the liquidator's counterparty, not the victim


async def test_hydrate_twap_merges_slices_and_is_incremental(tmp_path):
    from hlscout.ingest.hydrate import hydrate_twap, last_twap_time, raw_path

    addr = "0x" + "3" * 40
    base = pl.DataFrame([{"time": 1000, "coin": "ETH", "px": 100.0, "sz": 1.0, "side": "B", "dir": "",
                          "start_position": 0.0, "closed_pnl": 0.0, "fee": 0.0, "crossed": True, "oid": 1,
                          "tid": 1, "twap_id": None, "fee_token": "USDC", "liquidation": None,
                          "hash": "h"}], schema=FILL_SCHEMA)
    p = raw_path(tmp_path, "fills", addr)
    p.parent.mkdir(parents=True)
    base.write_parquet(p)
    calls = []

    class Info:
        async def post(self, payload, lane=None):
            calls.append(payload["startTime"])
            return [{"twapId": 7, "fill": {"coin": "ETH", "px": "101", "sz": "2", "side": "B", "time": 2000,
                                           "startPosition": "1.0", "dir": "Open Long", "closedPnl": "0.0",
                                           "hash": "0x0", "oid": 5, "crossed": True, "fee": "0.1", "tid": 99,
                                           "feeToken": "USDC", "twapId": None}}]

    assert await hydrate_twap(Info(), addr, tmp_path) == 1
    df = pl.read_parquet(p)
    assert df.height == 2 and df.filter(pl.col("tid") == 99)["twap_id"][0] == 7
    assert last_twap_time(tmp_path, addr) == 2000
    await hydrate_twap(Info(), addr, tmp_path)
    assert calls[1] == 1999 and pl.read_parquet(p).height == 2  # resumes from the last slice, no duplicates


def test_plan_backfill_targets_span_before_reliable_window(tmp_path):
    import json

    from hlscout.archive.backfill import plan_backfill
    from hlscout.ingest.hydrate import LEDGER_SCHEMA, raw_path

    addr = "0x" + "4" * 40
    day = 86_400_000
    t0 = 1_760_000_000_000  # Oct 2025: inside Hypedexer's measured coverage
    rows = []
    for i, (t, side, sp) in enumerate([(t0, "B", 0.0), (t0 + day, "A", 10.0),          # old, clean
                                       (t0 + 100 * day, "B", 50.0), (t0 + 101 * day, "A", 60.0)]):  # break at +100d
        rows.append({"time": t, "coin": "BTC", "px": 100.0, "sz": 10.0, "side": side, "dir": "", "start_position": sp,
                     "closed_pnl": 0.0, "fee": 0.0, "crossed": True, "oid": i, "tid": i, "twap_id": None,
                     "fee_token": "USDC", "liquidation": None, "hash": "h"})
    for kind, df in (("fills", pl.DataFrame(rows, schema=FILL_SCHEMA)),
                     ("ledger", pl.DataFrame([{"time": t0 - 30 * day, "hash": "x", "type": "deposit", "usdc": 1.0,
                                               "user": None, "destination": None, "token": None, "amount": None,
                                               "to_perp": None, "fee": None, "raw_json": "{}"}], schema=LEDGER_SCHEMA))):
        p = raw_path(tmp_path, kind, addr)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(p)
    pp = raw_path(tmp_path, "portfolio", addr).with_suffix(".json")
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps({"perpAllTime": {"accountValueHistory": [[t0 - 30 * day, "1000"]], "pnlHistory": [[t0 - 30 * day, "0"]]}}))
    plan = plan_backfill(tmp_path, addr)
    assert plan["start"] == t0 - 30 * day and plan["end"] == t0 + 100 * day + 1   # up to just after the last material break
    assert plan["days"] > 129 and plan["est_credits"] > 0
