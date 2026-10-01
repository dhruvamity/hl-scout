"""Link graph and clusters (plan §6.2): hard + transfer edges, union-find components.

Dust transfers (airdrop spam) and hub addresses (exchanges, bridges, protocol wallets) are not
links: edges need a minimum USD value, and a node touching more than `hub_degree` distinct
counterparties is treated as a hub and cannot join clusters.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import polars as pl

TRANSFER_TYPES = ("internalTransfer", "send", "spotTransfer", "subAccountTransfer")
SYSTEM_PREFIX = "0x2000000000000000000000000000000000"  # spot-deployer / system addresses


@dataclass
class Edge:
    src: str
    dst: str
    kind: str
    weight: float
    first_ts: int
    last_ts: int
    n: int = 1


@dataclass
class Graph:
    edges: dict[tuple[str, str, str], Edge] = field(default_factory=dict)
    hubs: set[str] = field(default_factory=set)

    def add(self, src: str, dst: str, kind: str, weight: float, ts: int) -> None:
        src, dst = src.lower(), dst.lower()
        if src == dst:
            return
        k = (src, dst, kind)
        e = self.edges.get(k)
        if e is None:
            self.edges[k] = Edge(src, dst, kind, weight, ts, ts)
        else:
            e.weight += weight
            e.first_ts, e.last_ts, e.n = min(e.first_ts, ts), max(e.last_ts, ts), e.n + 1


def edges_from_ledger(g: Graph, address: str, ledger: pl.DataFrame, min_usd: float = 100.0) -> None:
    if ledger.is_empty():
        return
    rows = ledger.filter(pl.col("type").is_in(TRANSFER_TYPES)).to_dicts()
    me = address.lower()
    for r in rows:
        u, d = (r.get("user") or "").lower(), (r.get("destination") or "").lower()
        if not u or not d or (me not in (u, d)):
            continue
        usd = abs(r.get("usdc") or 0.0) if (r.get("token") in (None, "USDC")) else 0.0
        if usd < min_usd:
            continue
        g.add(u, d, r["type"], usd, int(r["time"]))


def edges_from_meta(g: Graph, address: str, role: dict | None, subs: list | None,
                    extra_agents: list | None) -> None:
    """Hard links: userRole, subAccounts, extraAgents."""
    t = int(__import__("time").time() * 1000)
    role = role or {}
    if role.get("role") == "subAccount":
        master = (role.get("data") or {}).get("master")
        if master:
            g.add(master, address, "subaccount", 0.0, t)
    if role.get("role") == "agent":
        master = (role.get("data") or {}).get("user")
        if master:
            g.add(master, address, "agent", 0.0, t)
    for s in subs or []:
        sa = s.get("subAccountUser")
        if sa:
            g.add(address, sa, "subaccount", 0.0, t)
    for a in extra_agents or []:
        ad = a.get("address")
        if ad:
            g.add(address, ad, "agent", 0.0, t)


def find_hubs(g: Graph, hub_degree: int = 20) -> set[str]:
    nbrs: dict[str, set[str]] = defaultdict(set)
    for e in g.edges.values():
        nbrs[e.src].add(e.dst)
        nbrs[e.dst].add(e.src)
    return {n for n, s in nbrs.items() if len(s) > hub_degree or n.startswith(SYSTEM_PREFIX)}


def clusters(g: Graph, hub_degree: int = 20) -> dict[str, list[str]]:
    """Connected components over non-hub nodes; returns {cluster_id: sorted members} (size >= 2)."""
    g.hubs = find_hubs(g, hub_degree)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in g.edges.values():
        if e.src in g.hubs or e.dst in g.hubs:
            continue
        a, b = find(e.src), find(e.dst)
        if a != b:
            parent[max(a, b)] = min(a, b)
    comp: dict[str, list[str]] = defaultdict(list)
    for n in list(parent):
        comp[find(n)].append(n)
    return {f"c_{k[2:10]}": sorted(v) for k, v in comp.items() if len(v) >= 2}


def persist(con: Any, g: Graph, cl: dict[str, list[str]]) -> None:
    con.execute("BEGIN")
    con.execute("DELETE FROM links")
    con.execute("DELETE FROM clusters")
    for e in g.edges.values():
        con.execute("INSERT INTO links VALUES (?,?,?,?,?,?,?)",
                    (e.src, e.dst, e.kind, e.weight, e.first_ts, e.last_ts, str(e.n)))
    for cid, members in cl.items():
        con.execute("INSERT INTO clusters VALUES (?,?,?,?)", (cid, json.dumps(members), "transfer", 1.0))
        for m in members:
            con.execute("UPDATE addresses SET cluster_id=? WHERE address=?", (cid, m))
    con.execute("COMMIT")
