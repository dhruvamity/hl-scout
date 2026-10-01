import json

import polars as pl

from hlscout.ingest.hydrate import FILL_SCHEMA, FUNDING_SCHEMA, LEDGER_SCHEMA, raw_path
from hlscout.storage import connect_state
from hlscout.validation.forward import freeze, report
from tests.helpers import DAY, Wallet


def test_freeze_and_report(tmp_path):
    con = connect_state(tmp_path)
    addr = "0x" + "2" * 40
    w = Wallet()
    w.trip(w.t0, "BTC", "B", 1.0, 100.0, 90.0)             # before snapshot: loss
    w.trip(w.t0 + 10 * DAY, "BTC", "B", 1.0, 100.0, 110.0)  # after snapshot: win
    for kind, df in (("fills", pl.DataFrame(w.fills, schema=FILL_SCHEMA)),
                     ("funding", pl.DataFrame([], schema=FUNDING_SCHEMA)),
                     ("ledger", pl.DataFrame([], schema=LEDGER_SCHEMA))):
        p = raw_path(tmp_path, kind, addr)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(p)
    pp = raw_path(tmp_path, "portfolio", addr).with_suffix(".json")
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps({"perpAllTime": {"accountValueHistory": [[0, "1000"]], "pnlHistory": []}}))
    con.execute("INSERT INTO scores(entity, run_id, metrics_json, score, stage, category) "
                "VALUES (?, 'latest', '{}', 80, 'qualified', 'MDT')", (addr,))
    assert freeze(con, snap_ts=w.t0 + 5 * DAY) == 1
    r = report(con, tmp_path, w.t0 + 5 * DAY, now_ms=w.t0 + 40 * DAY)
    assert r["listed"] == 1 and r["active"] == 1 and r["hit_rate"] == 1.0
    assert abs(r["wallets"][0]["net"] - (10 - 0.1)) < 1e-6
