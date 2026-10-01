import json

import polars as pl

from hlscout.config import ScreenCfg
from hlscout.ingest.leaderboard import diff, parse, register, snapshot
from hlscout.ingest.screen import screen_s1
from hlscout.ingest.seeds import extract_addresses
from hlscout.storage import connect_state


def row(addr, av, vm, vall, pm, pall, rall=0.5):
    def w(p, v, r=0.1):
        return {"pnl": str(p), "roi": str(r), "vlm": str(v)}
    return {"ethAddress": addr, "accountValue": str(av), "displayName": None,
            "windowPerformances": [["day", w(0, 0)], ["week", w(0, 0)], ["month", w(pm, vm)],
                                   ["allTime", w(pall, vall, rall)]]}


def test_parse_and_screen(tmp_path):
    rows = [
        row("0x" + "1" * 40, 50000, 500_000, 5_000_000, 100, 1000),   # keep
        row("0x" + "2" * 40, 50000, 0, 0, 0, 1000),                   # zero volume
        row("0x" + "3" * 40, 1000, 500_000, 5_000_000, 1, 10),        # low equity
        row("0x" + "4" * 40, 50000, 500_000, 5_000_000, 1, -10, -0.1),  # all-time loss
        row("0x" + "4" + "0" * 39, 50000, 500_000, 5_000_000, 1, 10),   # system prefix? no
        row("0x4000000000000000000000000000000000000001", 9e9, 9e9, 9e9, 1, 1),  # backstop
    ]
    p = tmp_path / "lb.json"
    p.write_text(json.dumps({"leaderboardRows": rows}))
    df = parse(p)
    res = screen_s1(df, ScreenCfg()).to_dicts()
    by = {r["address"]: r for r in res}
    assert by["0x" + "1" * 40]["keep"]
    assert "zero_volume" in by["0x" + "2" * 40]["reasons"]
    assert "low_equity" in by["0x" + "3" * 40]["reasons"]
    assert "alltime_loss" in by["0x" + "4" * 40]["reasons"]
    assert "system_address" in by["0x4000000000000000000000000000000000000001"]["reasons"]


def test_tape_screen_only_when_old_enough():
    df = pl.DataFrame([row_flat for row_flat in [
        {"address": "0xa", "account_value": 1e5, "vlm_month": 1e6, "vlm_allTime": 1e7,
         "pnl_allTime": 1.0, "roi_allTime": 0.1}]])
    act = pl.DataFrame({"address": ["0xa"], "active_days": [3]})
    assert screen_s1(df, ScreenCfg(), tape_days=10, tape_active_days=act)["keep"][0]
    assert not screen_s1(df, ScreenCfg(), tape_days=90, tape_active_days=act)["keep"][0]


def test_registry_diff_snapshot_seeds(tmp_path):
    con = connect_state(tmp_path)
    assert register(con, ["0xa", "0xb"], "leaderboard") == 2
    assert register(con, ["0xb", "0xc"], "x") == 1
    assert con.execute("SELECT sources FROM addresses WHERE address='0xb'").fetchone()[0] == "leaderboard,x"
    register(con, ["0xb"], "x")
    assert con.execute("SELECT sources FROM addresses WHERE address='0xb'").fetchone()[0] == "leaderboard,x"
    prev = pl.DataFrame({"address": ["0xa", "0xb"]})
    cur = pl.DataFrame({"address": ["0xb", "0xc"]})
    assert diff(prev, cur) == {"new": ["0xc"], "gone": ["0xa"]}
    assert snapshot(cur, tmp_path, "2026-10-01").exists()
    text = "claim 0xAbCdEf0123456789abcdef0123456789ABCDEF01 and again 0xabcdef0123456789abcdef0123456789abcdef01"
    assert extract_addresses(text) == ["0xabcdef0123456789abcdef0123456789abcdef01"]
