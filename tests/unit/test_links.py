import polars as pl

from hlscout.detectors.multiwallet import (
    ClusterCtx,
    d_h1_cross_hedge,
    d_h3_wash,
    d_h4_lottery,
    d_h5_unlinked_twin,
    d_m7_rotation,
    hedge_ratio,
)
from hlscout.ingest.hydrate import FILL_SCHEMA, LEDGER_SCHEMA
from hlscout.links.graph import Graph, clusters, edges_from_ledger
from tests.helpers import DAY, HOUR, Wallet, clean_wallet

A = "0x" + "a" * 40
B = "0x" + "b" * 40
C = "0x" + "c" * 40
D = "0x" + "d" * 40


def wallet_fills(trips):
    w = Wallet()
    for t, side, hold, px, ex in trips:
        w.trip(t, "BTC", side, sz=10.0, px=px, exit_px=ex, hold=hold)
    return pl.DataFrame(w.fills, schema=FILL_SCHEMA)


def ledger(rows):
    return pl.DataFrame([{"time": t, "hash": f"h{t}", "type": ty, "usdc": u, "user": a, "destination": b,
                          "token": "USDC", "amount": u, "to_perp": None, "fee": 0.0, "raw_json": "{}"}
                         for t, ty, u, a, b in rows], schema=LEDGER_SCHEMA)


def test_clusters_link_transfers_ignore_dust_and_hubs():
    g = Graph()
    edges_from_ledger(g, A, ledger([(1, "internalTransfer", 5000.0, A, B), (2, "send", 3.0, A, C)]))
    cl = clusters(g)
    assert list(cl.values()) == [sorted([A, B])]
    # a hub touching many counterparties never merges unrelated wallets
    g2 = Graph()
    hub = "0x" + "9" * 40
    for i in range(30):
        g2.add(f"0x{i:040x}", hub, "send", 1000.0, i)
    assert clusters(g2) == {}


def test_cross_wallet_hedge_detected():
    t = 1_700_000_000_000
    long_ = wallet_fills([(t, "B", 10 * HOUR, 100, 101)])
    short = wallet_fills([(t, "A", 10 * HOUR, 100, 99)])
    cc = ClusterCtx("c1", [A, B], {A: long_, B: short})
    hr, _ = hedge_ratio(cc)
    assert hr > 0.9
    ctx = clean_wallet().ctx()
    assert d_h1_cross_hedge(ctx, cc).severity == "VETO"


def test_independent_wallets_not_hedged():
    t = 1_700_000_000_000
    a = wallet_fills([(t, "B", 5 * HOUR, 100, 101)])
    b = wallet_fills([(t + 6 * HOUR, "B", 5 * HOUR, 100, 101)])
    cc = ClusterCtx("c1", [A, B], {A: a, B: b})
    assert hedge_ratio(cc)[0] < 0.05


def tape(rows):
    return pl.DataFrame(rows, schema={"time": pl.Int64, "coin": pl.Utf8, "px": pl.Float64, "sz": pl.Float64,
                                      "side": pl.Utf8, "tid": pl.Int64, "hash": pl.Utf8,
                                      "buyer": pl.Utf8, "seller": pl.Utf8})


def test_wash_trading_detected():
    ctx = clean_wallet().ctx()
    me = ctx.address
    rows = [(i * 1000, "BTC", 100.0, 1.0, "B", i, "h", me, B) for i in range(20)]
    rows += [(99_000 + i, "BTC", 100.0, 1.0, "B", 100 + i, "h", me, C) for i in range(10)]
    assert d_h3_wash(ctx, tape(rows), [me, B]).severity == "VETO"
    assert d_h3_wash(ctx, tape(rows), [me]).severity == "INFO"


def test_unlinked_twin_flagged():
    ctx = clean_wallet().ctx()
    me = ctx.address
    rows, tid = [], 0
    for k in range(8):  # me buys from a MM, twin sells to another MM seconds later, similar size
        t = k * 10 * 60_000
        tid += 1
        rows.append((t, "ETH", 100.0, 5.0, "B", tid, "h", me, "0x" + "e" * 40))
        tid += 1
        rows.append((t + 20_000, "ETH", 100.0, 5.1, "A", tid, "h", "0x" + "f" * 40, D))
        # D is the twin (seller)
    f = d_h5_unlinked_twin(ctx, tape(rows))
    assert f is not None and f.code == "D-H5" and f.evidence[0]["twin"] == D


def test_lottery_and_rotation():
    t = 1_700_000_000_000
    win = wallet_fills([(t, "B", HOUR, 100, 150)])
    lose1 = wallet_fills([(t + DAY, "B", HOUR, 100, 60)])
    lose2 = wallet_fills([(t + 2 * DAY, "B", HOUR, 100, 60)])
    cc = ClusterCtx("c", [A, B, C], {A: win, B: lose1, C: lose2})
    ctx = clean_wallet().ctx()
    ctx.address = A
    assert d_h4_lottery(ctx, cc).severity == "VETO"
    # rotation: B loses, goes quiet; A starts a week later and is net positive but merged < 0
    loser = wallet_fills([(t, "B", HOUR, 100, 20)])
    fresh = wallet_fills([(t + 10 * DAY, "B", HOUR, 100, 105)])
    cc2 = ClusterCtx("c", [A, B], {B: loser, A: fresh})
    assert d_m7_rotation(ctx, cc2).severity == "VETO"
