"""Markdown report: two category leaderboards with every pass/fail reason (plan §8.2)."""

from __future__ import annotations

from datetime import UTC, datetime

LINKS = ("https://hypurrscan.io/address/{a}", "https://hyperdash.com/address/{a}",
         "https://hyperx.trade/hyperliquid/trader?address={a}")


def _row(r: dict) -> str:
    m, a = r["metrics"], r["address"]
    return (f"| {r['rank']} | `{a}` | {r['score']} | {m['genuine_months']} | {m['twr_all']:.2f} | "
            f"{m['max_dd_twr']:.2f} | {m['sharpe']:.1f} | {m['tstat']:.1f}/{m['dsr_prob']:.2f} | "
            f"[HypurrScan]({LINKS[0].format(a=a)}) · [Hyperdash]({LINKS[1].format(a=a)}) |")


def render(results: list[dict], n_scanned: int | None = None) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    stages: dict[str, int] = {}
    for r in results:
        stages[r["stage"]] = stages.get(r["stage"], 0) + 1
    out = [f"# HL-Scout report ({now})", "",
           "Research tooling, not financial advice. Qualified wallets still need forward validation.", "",
           f"Wallets assessed: {n_scanned or len(results)} · stages: "
           + ", ".join(f"{k}={v}" for k, v in sorted(stages.items())), ""]
    for tier, tier_title, empty in (
            ("qualified", "Qualified", "_none qualified_"),
            ("provisional", "Provisional (integrity-clean, soft-gate misses: forward-tracked, not yet proven)",
             "_none provisional_")):
        for cat, title in (("MDT", "Manual Disciplined Traders"), ("ADT", "Algorithmic Disciplined Traders"),
                           ("UNSURE", "Unsure category (classifier confidence < 0.7)")):
            rows = sorted((r for r in results if r["stage"] == tier and r["category"]["category"] == cat),
                          key=lambda r: r["rank"])
            out += [f"## {tier_title.split(' (')[0]}: {title}", ""]
            if tier == "provisional" and cat == "MDT":
                out += [f"_{tier_title}_", ""]
            if not rows:
                out += [empty, ""]
                continue
            out += ["| # | Address | Score | Genuine months | TWR | Max DD | Sharpe | t / DSR | Links |",
                    "|---|---|---|---|---|---|---|---|---|"] + [_row(r) for r in rows] + [""]
    qa = [r for r in results if r["stage"] == "needs_qa"]
    if qa:
        out += ["## Needs QA (3+ flag families)", ""] + [
            f"- `{r['address']}`: {', '.join(r['verdict']['flags'])}" for r in qa] + [""]
    ref = [r for r in results if r["stage"] == "reformed"]
    if ref:
        out += ["## Reformed watch (clean only recently, not qualified)", ""] + [
            f"- `{r['address']}`: genuine months {r['metrics']['genuine_months']}" for r in ref] + [""]
    out += _near_misses(results)
    out += ["## Why wallets failed", ""]
    reasons: dict[str, int] = {}
    for r in results:
        if r["stage"] in ("vet_fail", "reformed"):
            for x in r["reasons"]:
                reasons[x] = reasons.get(x, 0) + 1
    out += [f"- {k}: {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])]
    return "\n".join(out) + "\n"


DERIVED = {"G10", "G1b"}  # consequences of a veto, not independent failures


def _near_misses(results: list[dict], n: int = 15) -> list[str]:
    """Wallets that came closest: fewest independent failing gates, then strongest t-stat."""
    cands = []
    for r in results:
        if r["stage"] != "vet_fail" or not r.get("gates"):
            continue
        failed = {g["gate"].split()[0] for g in r["gates"] if g["pass"] is False}
        core = failed - DERIVED
        cands.append((len(core) + (1 if r["verdict"]["vetoes"] else 0), -(r["metrics"].get("tstat") or 0), r, failed))
    cands.sort(key=lambda x: (x[0], x[1]))
    if not cands:
        return []
    out = ["## Closest misses (not qualified: review before trusting any of them)", "",
           "| Address | Cat | Vetoes | Other failing gates | t / DSR | Net 180d | Genuine mo. | Links |",
           "|---|---|---|---|---|---|---|---|"]
    for _, _, r, failed in cands[:n]:
        m, a = r["metrics"], r["address"]
        out.append(f"| `{a}` | {r['category']['category']} | {', '.join(r['verdict']['vetoes']) or '-'} | "
                   f"{', '.join(sorted(failed - DERIVED)) or '-'} | {m.get('tstat', 0):.1f}/{m.get('dsr_prob', 0):.2f} | "
                   f"{m.get('net_180d', 0):,.0f} | {m.get('genuine_months', 0)} | "
                   f"[HypurrScan]({LINKS[0].format(a=a)}) · [Hyperdash]({LINKS[1].format(a=a)}) |")
    return out + [""]
