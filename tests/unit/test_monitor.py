import sqlite3

from hlscout.monitor.alerts import Notifier
from hlscout.monitor.events import Envelope, Snap, check_triggers, diff_state, flock
from hlscout.monitor.run import poll_once, request_revet
from hlscout.storage import SCHEMA


def snap(ts, eq, ntl, pos):
    return Snap(ts, eq, ntl, {c: {"szi": s, "upnl": u, "liq": 1.0, "lev": 5} for c, (s, u) in pos.items()})


def test_diff_events():
    a = snap(1, 1000, 500, {"BTC": (1.0, 0)})
    b = snap(2, 1000, 900, {"BTC": (2.0, 0), "ETH": (-3.0, 0)})
    kinds = {(e.coin, e.event) for e in diff_state("0x1", a, b)}
    assert kinds == {("BTC", "add"), ("ETH", "open")}
    assert {e.event for e in diff_state("0x1", b, snap(3, 1000, 0, {}))} == {"close"}


def test_liquidation_and_leverage_and_rescue_triggers():
    prev = snap(1, 10_000, 50_000, {"BTC": (1.0, -3000)})
    cur = snap(2, 2_000, 0, {})
    assert any(e.event == "liquidation" for e in check_triggers("0x1", prev, cur, Envelope()))
    hot = snap(3, 1_000, 20_000, {"ETH": (5.0, 0)})
    assert any(e.event == "leverage_breach" for e in check_triggers("0x1", None, hot, Envelope()))
    under = snap(1, 10_000, 40_000, {"BTC": (1.0, -3000)})
    ev = check_triggers("0x1", under, under, Envelope(max_leverage=99), inflows=[(5, 2000.0)])
    assert any(e.event == "rescue_inflow" and e.revet for e in ev)


def test_flock():
    from hlscout.monitor.events import Event

    es = [Event("0xa", 0, "open", "BTC", 1, detail={"to": 1}), Event("0xb", 60_000, "open", "BTC", 1, detail={"to": 2}),
          Event("0xc", 60_000, "open", "ETH", 1, detail={"to": 1})]
    assert len(flock(es)) == 1


class FakeInfo:
    def __init__(self, states, ledger):
        self.states, self.ledger = list(states), ledger

    async def post(self, payload, lane=None):
        return self.states.pop(0) if payload["type"] == "clearinghouseState" else self.ledger


async def test_poll_trips_revet_and_alerts(tmp_path):
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO addresses(address, stage) VALUES ('0x1','qualified')")
    sent = []

    async def sender(t):
        sent.append(t)

    n = Notifier(tmp_path, sender=sender)
    dead = {"marginSummary": {"accountValue": "100", "totalNtlPos": "0"}, "assetPositions": []}
    prev = snap(1, 10_000, 50_000, {"BTC": (1.0, -3000)})
    await poll_once(FakeInfo([dead], []), con, n, "0x1", prev, Envelope(), [""], 0)
    assert any("liquidation" in t for t in sent)
    assert con.execute("SELECT stage FROM addresses WHERE address='0x1'").fetchone()[0] == "revet"
    assert con.execute("SELECT state FROM queue WHERE address='0x1'").fetchone()[0] == "pending"
    request_revet(con, "0x1")  # idempotent


def test_progress_snapshot_and_usage(tmp_path):
    from hlscout.monitor.progress import snapshot
    from hlscout.storage import connect_state, usage_recorder

    con = connect_state(tmp_path)
    rec = usage_recorder(tmp_path)
    rec("light_hydrate", 22)
    rec("light_hydrate", 22)
    con.execute("INSERT INTO queue(address, kind, lane, state) VALUES ('a','light','l','done'),('b','light','l','pending')")
    s = snapshot(tmp_path, con)
    assert s["queue"]["light"]["total"] == 2 and s["queue"]["light"]["done"] == 1
    assert s["api"]["by_lane_5min"]["light_hydrate"] == 44
