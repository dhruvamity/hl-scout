"""Cluster audit: build the link graph from cached raw data, then run multi-wallet detectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from hlscout.detectors.base import build_ctx
from hlscout.detectors.multiwallet import ClusterCtx, run_cluster_detectors
from hlscout.ingest.hydrate import raw_path
from hlscout.links.graph import Graph, clusters, edges_from_ledger, edges_from_meta, persist
from hlscout.recon.roundtrips import perp_only
from hlscout.recon.vet import load_raw


def build_graph(root: Path) -> Graph:
    g = Graph()
    for p in sorted((Path(root) / "raw" / "ledger").glob("*.parquet")):
        a = p.stem
        edges_from_ledger(g, a, pl.read_parquet(p))
        mp = raw_path(Path(root), "meta", a).with_suffix(".json")
        if mp.exists():
            import json

            m = json.loads(mp.read_text())
            edges_from_meta(g, a, m.get("role"), m.get("subaccounts"), m.get("extra_agents"))
    return g


def tape_slice(tape_root: Path, address: str, window_ms: int = 60_000) -> pl.DataFrame | None:
    """The address's own trades plus all trades on the same coin within +/-window of them."""
    files = list(Path(tape_root).glob("date=*/hour=*/*.parquet"))
    if not files:
        return None
    con = duckdb.connect(":memory:")
    # view definitions cannot take prepared parameters: inline the (locally generated) file list
    lst = ", ".join("'" + str(f).replace("'", "''") + "'" for f in files)
    con.execute(f"CREATE VIEW tape AS SELECT DISTINCT * FROM read_parquet([{lst}], union_by_name=true)")
    q = """
    WITH mine AS (SELECT * FROM tape WHERE buyer = ? OR seller = ?)
    SELECT DISTINCT t.* FROM tape t JOIN mine m
      ON t.coin = m.coin AND t.time BETWEEN m.time - ? AND m.time + ?"""
    df = con.execute(q, [address, address, window_ms, window_ms]).pl()
    return df if not df.is_empty() else None


def cluster_findings(root: Path, tape_root: Path, address: str, cl: dict[str, list[str]],
                     cfg: Any = None, graph: Graph | None = None) -> list:
    root = Path(root)
    members = next((m for m in cl.values() if address in m), None)
    cid = next((k for k, m in cl.items() if address in m), None)
    raw = load_raw(root, address)
    ctx = build_ctx(address, raw["fills"], raw["funding"], raw["ledger"], raw["portfolio"], cfg=cfg)
    cc = None
    if members:
        fills = {}
        for m in members:
            if raw_path(root, "fills", m).exists():
                fills[m] = perp_only(pl.read_parquet(raw_path(root, "fills", m)))
        from hlscout.links.graph import cluster_confidence

        cc = ClusterCtx(cid or "", members, fills,
                        confidence=cluster_confidence(graph, members) if graph is not None else 1.0)
    return run_cluster_detectors(ctx, cc, tape_slice(tape_root, address))


def unhydrated_members(root: Path, cl: dict[str, list[str]]) -> list[str]:
    return sorted({m for ms in cl.values() for m in ms if not raw_path(Path(root), "fills", m).exists()})


__all__ = ["build_graph", "cluster_findings", "clusters", "persist", "tape_slice", "unhydrated_members"]
