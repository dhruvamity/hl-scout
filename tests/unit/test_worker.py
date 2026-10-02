
from hlscout.config import Config
from hlscout.ingest.worker import enqueue, next_item, requeue_stale, s2_screen
from hlscout.storage import connect_state

NOW = 1_800_000_000_000
DAY = 86_400_000


def pf(first_age_d, pnl, eq):
    t0 = NOW - first_age_d * DAY
    return {"perpAllTime": {"accountValueHistory": [[t0, str(eq)], [NOW, str(eq)]],
                            "pnlHistory": [[t0, "0"], [NOW, str(pnl)]]}}


def test_s2_screen():
    cfg = Config()
    ok = lambda **k: s2_screen({"role": {"role": "user"}, "portfolio": pf(**k)}, cfg, NOW)
    assert ok(first_age_d=300, pnl=1000, eq=20000) == (True, "ok")
    assert ok(first_age_d=100, pnl=1000, eq=20000)[1] == "too_young"
    assert ok(first_age_d=300, pnl=-5, eq=20000)[1] == "perp_pnl<=0"
    assert ok(first_age_d=300, pnl=10, eq=100)[1] == "low_median_equity"
    assert s2_screen({"role": {"role": "vault"}, "portfolio": pf(300, 1, 1e5)}, cfg, NOW)[1] == "role:vault"


def test_s2_coarse_gates():
    cfg = Config()
    base = {"role": None}
    deep_dd = {"perpAllTime": {"accountValueHistory": [[NOW - 300 * DAY, "10000"], [NOW - 100 * DAY, "10000"],
                                                       [NOW, "10000"]],
                               "pnlHistory": [[NOW - 300 * DAY, "0"], [NOW - 100 * DAY, "9000"],
                                              [NOW, "2000"]]}}
    assert s2_screen({**base, "portfolio": deep_dd}, cfg, NOW)[1].startswith("coarse_dd")
    stale = {"perpAllTime": {"accountValueHistory": [[NOW - 300 * DAY, "10000"], [NOW - 60 * DAY, "10000"],
                                                     [NOW, "10000"]],
                             "pnlHistory": [[NOW - 300 * DAY, "0"], [NOW - 60 * DAY, "500"], [NOW, "500"]]}}
    assert s2_screen({**base, "portfolio": stale}, cfg, NOW)[1] == "inactive_recent"
    hot = {**base, "portfolio": pf(300, 1000, 20000),
           "state": {"marginSummary": {"accountValue": "1000", "totalNtlPos": "50000"}}}
    assert s2_screen(hot, cfg, NOW)[1] == "open_leverage"


def test_light_first_then_deep_by_score_with_cap(tmp_path):
    from hlscout.ingest.worker import URGENT

    con = connect_state(tmp_path)
    enqueue(con, ["0xl1"], "light", "light_hydrate")
    enqueue(con, ["0xd_low"], "deep", "deep_vet", priority=1.0)
    enqueue(con, ["0xd_high"], "deep", "deep_vet", priority=9.0)
    enqueue(con, ["0xurgent"], "deep", "deep_vet", priority=URGENT)
    order = [next_item(con, deep_cap=1)[1] for _ in range(3)]
    assert order == ["0xurgent", "0xl1", "0xd_high"]
    assert next_item(con, deep_cap=1) is None  # cap reached: 0xd_low waits


def test_queue_idempotent_and_deep_first(tmp_path):
    con = connect_state(tmp_path)
    assert enqueue(con, ["0xa", "0xb"], "light", "light_hydrate") == 2
    assert enqueue(con, ["0xa"], "light", "light_hydrate") == 0
    enqueue(con, ["0xb"], "deep", "deep_vet", priority=1)
    first = next_item(con)
    assert first[1:] == ("0xa", "light")  # cheap screens go before deep vets
    requeue_stale(con)  # simulated crash: running -> pending
    assert next_item(con)[1:] == ("0xa", "light")


async def test_hft_prescreen():
    from hlscout.ingest.worker import hft_prescreen

    class Info:
        def __init__(self, rows):
            self.rows = rows

        async def post(self, payload, lane=None):
            return self.rows

    cfg = Config()
    busy = [{"time": NOW - i * 1000, "crossed": True} for i in range(2000)]  # 2000 fills in 33 minutes
    assert (await hft_prescreen(Info(busy), "0x1", cfg))["trades_per_day"] > 300
    calm = [{"time": NOW - i * 3_600_000, "crossed": True} for i in range(2000)]
    assert await hft_prescreen(Info(calm), "0x1", cfg) is None
    makers = [{"time": NOW - i * 3_600_000, "crossed": False} for i in range(2000)]
    assert (await hft_prescreen(Info(makers), "0x1", cfg))["maker_share"] == 1.0
    assert await hft_prescreen(Info([{"time": NOW, "crossed": True}]), "0x1", cfg) is None


def test_refresh_queue_runs_after_light_and_ignores_deep_cap(tmp_path):
    from hlscout.ingest.worker import enqueue_refresh

    con = connect_state(tmp_path)
    enqueue(con, ["0xl"], "light", "light_hydrate")
    enqueue(con, ["0xd"], "deep", "deep_vet", priority=3.0)
    assert enqueue_refresh(con, ["0xr"]) == 0 and con.execute("SELECT COUNT(*) FROM queue WHERE kind='refresh'").fetchone()[0] == 1
    order = [next_item(con, deep_cap=0)[1] for _ in range(2)]  # cap 0 blocks normal deep vets, not refresh
    assert order == ["0xl", "0xr"] and next_item(con, deep_cap=0) is None
    con.execute("UPDATE queue SET state='done' WHERE address='0xr'")
    assert enqueue_refresh(con, ["0xr"]) == 1  # re-armed for the next cycle


def test_tape_candidates(tmp_path):
    import polars as pl

    from hlscout.ingest.screen import tape_candidates

    for d in range(40):
        pl.DataFrame({"address": ["0xa", "0xmm", "0xnew"], "date": [f"2026-09-{d:02d}"] * 3,
                      "trades": [20, 5000, 5], "notional": [5e4, 1e8, 200.0],
                      "maker_share_proxy": [0.3, 0.95, 0.4]}).write_parquet(tmp_path / f"date=2026-09-{d:02d}.parquet")
    r = tape_candidates(tmp_path, min_active_days=30).sort("address")
    assert dict(zip(r["address"], r["keep"], strict=True)) == {"0xa": True, "0xmm": False, "0xnew": False}


def _api_fills(n_trips, hold_s, liq=False, base=NOW - 400 * DAY):
    rows, tid = [], 0
    for k in range(n_trips):
        t = base + k * (hold_s + 3600) * 1000
        for side, dt_, d in (("B", 0, "Open Long"), ("A", hold_s * 1000, "Close Long")):
            tid += 1
            rows.append({"coin": "BTC", "px": "100", "sz": "1", "side": side, "time": t + dt_, "startPosition":
                         "0.0" if side == "B" else "1.0", "dir": d, "closedPnl": "0", "hash": "h", "oid": tid,
                         "crossed": True, "fee": "0.01", "tid": tid, "feeToken": "USDC",
                         "liquidation": {"liquidatedUser": "0x1", "markPx": "1", "method": "market"}
                         if liq and k == 3 and side == "A" else None})
    return rows


def test_quick_vet_rules():
    from hlscout.ingest.worker import quick_vet

    cfg = Config()
    assert quick_vet(_api_fills(60, 1800), cfg, "0x1") is None                      # 30-minute holds: fine
    assert "own_liquidation_fills" in quick_vet(_api_fills(60, 1800, liq=True), cfg, "0x1")
    r = quick_vet(_api_fills(60, 3 * 86_400), cfg, "0x1")                            # 3-day holds: swing trader
    assert r and r["median_hold_s"] == 3 * 86_400
    assert quick_vet(_api_fills(60, 20), cfg, "0x1")["median_hold_s"] == 20         # 20-second scalper
