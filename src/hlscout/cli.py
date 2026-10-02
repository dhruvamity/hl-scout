from __future__ import annotations

import typer

from hlscout.config import load_config
from hlscout.logging_setup import setup_logging
from hlscout.storage import connect_state, usage_recorder

app = typer.Typer(help="HL-Scout: read-only Hyperliquid trader scanner")


@app.callback()
def _main() -> None:
    setup_logging()


@app.command()
def init(config: str = "config/config.yaml") -> None:
    """Create the data dir and SQLite state."""
    cfg = load_config(config)
    connect_state(cfg.data_dir)
    typer.echo(f"initialised {cfg.data_dir}/state.sqlite")


@app.command()
def tape(config: str = "config/config.yaml", duration_s: int = 0) -> None:
    """Record all trades to Parquet (runs until stopped, or duration_s if > 0)."""
    import asyncio
    from pathlib import Path

    import websockets

    from hlscout.clients.info import InfoClient
    from hlscout.clients.ratelimit import RateLimiter
    from hlscout.ingest.tape import TapeRecorder, TradeBuffer, fetch_coins, nightly_maintenance

    cfg = load_config(config)
    root = Path(cfg.data_dir)
    state = connect_state(root)
    limiter = RateLimiter(cfg.api.weight_per_min, cfg.api.headroom, cfg.api.lanes)
    info = InfoClient(limiter, cfg.api.info_url, usage=usage_recorder(root))

    async def main() -> None:
        async def post(p: dict) -> object:
            return await info.post(p, lane="monitor")  # reserved lane: the tape must never starve

        async def gapfill(coin: str) -> list[dict]:
            return await info.post({"type": "recentTrades", "coin": coin}, lane="monitor")

        rec = TapeRecorder(
            TradeBuffer(root / "tape"), state, lambda: fetch_coins(post),
            lambda: websockets.connect(cfg.api.ws_url, ping_interval=None),
            gapfill_fn=gapfill, ping_s=cfg.tape.ping_s,
        )
        rec.heartbeat_path = root / "tape.heartbeat"
        if duration_s:
            asyncio.get_running_loop().call_later(duration_s, rec.stop.set)
        run = asyncio.create_task(rec.run())
        maint = asyncio.create_task(nightly_maintenance(root, cfg.tape.retain_raw_days))
        if duration_s:
            await rec.stop.wait()
            run.cancel()
            maint.cancel()
            rec.buffer.flush()
        else:
            await run

    asyncio.run(main())


@app.command()
def universe(config: str = "config/config.yaml", seeds: str = "", local_file: str = "") -> None:
    """Snapshot the leaderboard, update the registry, run the S1 screen, diff vs yesterday."""
    from datetime import UTC, datetime
    from pathlib import Path

    from hlscout.ingest import leaderboard as lb
    from hlscout.ingest.screen import screen_s1
    from hlscout.ingest.seeds import load_seed_file

    cfg = load_config(config)
    root = Path(cfg.data_dir)
    con = connect_state(root)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    raw = Path(local_file) if local_file else lb.download(
        cfg.screen.leaderboard_url, root / "leaderboard" / "raw.json")
    df = lb.parse(raw)
    d = lb.diff(lb.previous_snapshot(root, today), df)
    lb.snapshot(df, root, today)
    new = lb.register(con, df["address"].to_list(), "leaderboard")
    if seeds:
        new += lb.register(con, load_seed_file(Path(seeds)), "seed")
    res = screen_s1(df, cfg.screen)
    keep = res.filter(res["keep"])
    con.execute("BEGIN")
    for a in keep["address"].to_list():
        con.execute("UPDATE addresses SET stage='s1_pass' WHERE address=? AND stage='discovered'", (a,))
    for a in res.filter(~res["keep"])["address"].to_list():
        con.execute("UPDATE addresses SET stage='screened_out' WHERE address=? AND stage='discovered'", (a,))
    con.execute("COMMIT")
    typer.echo(f"rows={df.height} new_registry={new} board_new={len(d['new'])} "
               f"board_gone={len(d['gone'])} s1_pass={keep.height}")
    reasons = res.explode("reasons").group_by("reasons").len().sort("len", descending=True)
    typer.echo(str(reasons))


@app.command()
def score(config: str = "config/config.yaml", out: str = "reports/latest.md") -> None:
    """Assess every hydrated address from cached raw data, rank, write the report + scores table."""
    import json
    from pathlib import Path

    from hlscout.links.audit import build_graph, cluster_findings, clusters
    from hlscout.recon.vet import assess_cached
    from hlscout.reports.daily import render
    from hlscout.scoring.engine import rank_qualified

    cfg = load_config(config)
    root = Path(cfg.data_dir)
    con = connect_state(root)
    from hlscout.ingest.hydrate import raw_path

    def complete(a: str) -> bool:  # meta.json is written last by hydrate_deep
        return all(raw_path(root, k, a).with_suffix(".json" if k in ("meta", "portfolio") else ".parquet").exists()
                   for k in ("fills", "funding", "ledger", "meta", "portfolio"))

    addrs = sorted(p.stem for p in (root / "raw" / "fills").glob("*.parquet") if complete(p.stem))
    n_trials = max(len(addrs), 5000)
    results = []
    for a in addrs:
        try:
            results.append(assess_cached(root, a, cfg, n_trials=n_trials))
        except Exception as e:  # noqa: BLE001 - one bad wallet must not sink the report
            typer.echo(f"skip {a[:10]}: {type(e).__name__}: {e}")
    # multi-wallet pass (plan §6.2): only finalists are worth the tape query
    cl = clusters(build_graph(root))
    for i, r in enumerate(results):
        if r["stage"] in ("qualified", "needs_qa", "reformed"):
            extra = cluster_findings(root, root / "tape", r["address"], cl, cfg)
            if extra:
                results[i] = assess_cached(root, r["address"], cfg, n_trials=n_trials, extra=extra)
    rank_qualified(results)
    con.execute("BEGIN")
    con.execute("DELETE FROM scores WHERE run_id='latest'")  # one current row per wallet
    for r in results:
        con.execute("INSERT INTO scores(entity, run_id, gates_json, metrics_json, score, stage, category, p_algo)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (r["address"], "latest", json.dumps(r["gates"], default=str),
                     json.dumps({k: v for k, v in r["metrics"].items() if k != "months"}, default=str),
                     r.get("score"), r["stage"], r["category"]["category"], r["category"]["p_algo"]))
        con.execute("UPDATE addresses SET stage=? WHERE address=?", (r["stage"], r["address"]))
    con.execute("COMMIT")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(render(results))
    typer.echo(f"assessed {len(results)}; report -> {out}")


@app.command()
def links(config: str = "config/config.yaml", enqueue_members: bool = True) -> None:
    """Build the link graph + clusters from cached raw data; queue unhydrated cluster members."""
    from pathlib import Path

    from hlscout.ingest import worker as w
    from hlscout.links.audit import build_graph, clusters, persist, unhydrated_members

    cfg = load_config(config)
    root = Path(cfg.data_dir)
    con = connect_state(root)
    g = build_graph(root)
    cl = clusters(g)
    persist(con, g, cl)
    typer.echo(f"edges={len(g.edges)} hubs={len(g.hubs)} clusters={len(cl)} "
               f"max_size={max((len(m) for m in cl.values()), default=0)}")
    if enqueue_members:
        todo = unhydrated_members(root, cl)
        typer.echo(f"queued {w.enqueue(con, todo, 'deep', 'light_hydrate', priority=-1)} cluster members")


@app.command()
def backfill(config: str = "config/config.yaml", limit: int = 0) -> None:
    """Archive pass for history_truncated wallets (needs HYPEDEXER_API_KEY in the environment)."""
    import asyncio
    from pathlib import Path

    from hlscout.archive.backfill import backfill_address, truncated_wallets
    from hlscout.archive.hypedexer import getter_from_env

    g = getter_from_env()
    if g is None:
        typer.echo("HYPEDEXER_API_KEY is not set; archive backfill needs it (free tier: 5k credits/month).")
        raise typer.Exit(1)
    root = Path(load_config(config).data_dir)
    todo = truncated_wallets(root)
    todo = todo[:limit] if limit else todo

    from hlscout.archive.hypedexer import CreditBudget, OutOfCredits

    budget = CreditBudget(connect_state(root))
    typer.echo(f"credits remaining this month: {budget.remaining()}")

    async def main() -> None:
        for a in todo:
            try:
                typer.echo(f"{a[:10]} {await backfill_address(g, root, a, budget)}")
            except OutOfCredits as e:
                typer.echo(f"stopping: {e}")
                return

    typer.echo(f"{len(todo)} truncated wallets")
    asyncio.run(main())


@app.command()
def monitor(config: str = "config/config.yaml", port: int = 8765) -> None:
    """Watchlist monitor (state polling + alerts) with the local dashboard on 127.0.0.1."""
    import asyncio
    import threading
    from pathlib import Path

    from hlscout.clients.info import InfoClient
    from hlscout.clients.ratelimit import RateLimiter
    from hlscout.monitor.dashboard import serve
    from hlscout.monitor.run import run_monitor

    cfg = load_config(config)
    root = Path(cfg.data_dir)
    con = connect_state(root)
    srv = serve(root, lambda: connect_state(root), port, load_config(config).screen.deep_cap)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    typer.echo(f"dashboard http://127.0.0.1:{port}  health http://127.0.0.1:{port}/health")

    async def main() -> None:
        info = InfoClient(RateLimiter(cfg.api.weight_per_min, cfg.api.headroom, cfg.api.lanes),
                          cfg.api.info_url, usage=usage_recorder(root))
        await run_monitor(info, con, root, asyncio.Event())

    asyncio.run(main())


@app.command()
def health(config: str = "config/config.yaml") -> None:
    """Print health problems (exit 1 if any)."""
    from pathlib import Path

    from hlscout.ops.health import check

    root = Path(load_config(config).data_dir)
    problems = check(root, connect_state(root))
    typer.echo("\n".join(problems) if problems else "ok")
    raise typer.Exit(1 if problems else 0)


@app.command()
def scheduler(config: str = "config/config.yaml") -> None:
    """Daily jobs (universe, links, score, backup) + health alerts."""
    import asyncio
    from pathlib import Path

    from hlscout.ops.scheduler import run_scheduler

    root = Path(load_config(config).data_dir)
    asyncio.run(run_scheduler(root, config, connect_state(root), asyncio.Event()))


@app.command()
def freeze(config: str = "config/config.yaml") -> None:
    """Freeze the current ranked list for forward validation (P10)."""
    from hlscout.validation.forward import freeze as fz

    con = connect_state(load_config(config).data_dir)
    typer.echo(f"froze {fz(con)} wallets")


@app.command()
def forward(config: str = "config/config.yaml", snap_ts: int = 0) -> None:
    """Live-vs-backtest report for a frozen list (latest snapshot by default)."""
    from pathlib import Path

    from hlscout.validation.forward import report

    cfg = load_config(config)
    con = connect_state(cfg.data_dir)
    ts = snap_ts or (con.execute("SELECT MAX(snap_ts) FROM forward_lists").fetchone()[0] or 0)
    if not ts:
        typer.echo("no frozen list; run `hlscout freeze` first")
        raise typer.Exit(1)
    r = report(con, Path(cfg.data_dir), ts)
    typer.echo({k: v for k, v in r.items() if k != "wallets"})


@app.command()
def tracker(config: str = "config/config.yaml", port: int = 8765) -> None:
    """Live progress page on http://127.0.0.1:<port> (no polling of the API; reads local state)."""
    from pathlib import Path

    from hlscout.monitor.dashboard import serve

    root = Path(load_config(config).data_dir)
    srv = serve(root, lambda: connect_state(root), port, load_config(config).screen.deep_cap)
    typer.echo(f"tracker http://127.0.0.1:{port}")
    srv.serve_forever()


@app.command()
def worker(config: str = "config/config.yaml", enqueue_s1: bool = True, limit: int = 0) -> None:
    """Queue consumer: S2 light screen -> deep hydrate -> assess, within the rate limit."""
    import asyncio
    from pathlib import Path

    from hlscout.clients.info import InfoClient
    from hlscout.clients.ratelimit import RateLimiter
    from hlscout.ingest import worker as w

    cfg = load_config(config)
    root = Path(cfg.data_dir)
    con = connect_state(root)
    if enqueue_s1:
        cands = w.candidates(root, con)
        cands = cands[:limit] if limit else cands
        typer.echo(f"enqueued {w.enqueue(con, cands, 'light', 'light_hydrate')} new (of {len(cands)})")

    async def main() -> None:
        info = InfoClient(RateLimiter(cfg.api.weight_per_min, cfg.api.headroom, cfg.api.lanes),
                          cfg.api.info_url, usage=usage_recorder(root))
        from hlscout.ingest.assets import ensure_asset_names

        await ensure_asset_names(info, root)
        await w.run_worker(info, con, root, cfg, asyncio.Event())

    asyncio.run(main())


@app.command()
def compact(date: str, config: str = "config/config.yaml") -> None:
    """Aggregate one day (YYYY-MM-DD) of tape into addr_day_stats."""
    from pathlib import Path

    from hlscout.ingest.tape import compact_day

    root = Path(load_config(config).data_dir)
    out = compact_day(root / "tape", root / "addr_day_stats", date)
    typer.echo(f"wrote {out}" if out else "no tape for that date")


@app.command()
def vet(address: str, config: str = "config/config.yaml") -> None:
    """Hydrate one address and print the audit (reconstruction + reconciliation)."""
    import asyncio
    from pathlib import Path

    from hlscout.clients.info import InfoClient
    from hlscout.clients.ratelimit import RateLimiter
    from hlscout.recon.vet import vet_address

    cfg = load_config(config)
    root = Path(cfg.data_dir)

    async def main() -> dict:
        info = InfoClient(RateLimiter(cfg.api.weight_per_min, cfg.api.headroom, cfg.api.lanes),
                          cfg.api.info_url, usage=usage_recorder(root))
        try:
            return await vet_address(info, address.lower(), Path(cfg.data_dir))
        finally:
            await info.aclose()

    res = asyncio.run(main())
    for k, v in res.items():
        if k in ("round_trips", "curve", "findings"):
            continue
        typer.echo(f"{k}: {v}")
    for f in res["findings"]:
        if f.severity != "INFO":
            typer.echo(f"  [{f.severity}] {f.code}: {f.metrics or f.evidence[:2]}")




if __name__ == "__main__":
    app()
