
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
