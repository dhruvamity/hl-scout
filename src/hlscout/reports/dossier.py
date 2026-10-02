"""Per-wallet HTML dossier: gate table, detector evidence, monthly grades, equity curve, copy card, QA links."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any

from hlscout.reports.daily import LINKS

CSS = """body{font:14px/1.45 system-ui,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#1b2030}
table{border-collapse:collapse;width:100%;margin:8px 0 18px}td,th{border:1px solid #d9dce5;padding:4px 8px;text-align:left;vertical-align:top}
th{background:#f1f3f8}.pass{color:#117a3d;font-weight:600}.fail{color:#b3261e;font-weight:600}.na{color:#7a8194}
code{background:#f1f3f8;padding:1px 4px;border-radius:3px}h1{font-size:20px}h2{font-size:15px;margin-top:22px}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;background:#e8ecf5;margin-right:6px}"""


def _svg_curve(points: list[float], w: int = 900, h: int = 140) -> str:
    if len(points) < 2:
        return "<p class='na'>not enough daily history</p>"
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    xy = " ".join(f"{i * w / (len(points) - 1):.1f},{h - (p - lo) / span * (h - 8) - 4:.1f}"
                  for i, p in enumerate(points))
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}'><polyline fill='none' stroke='#3367d6' "
            f"stroke-width='1.6' points='{xy}'/></svg><div class='na'>flow-adjusted TWR index "
            f"{points[0]:.2f} → {points[-1]:.2f}, daily</div>")


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.3f}" if abs(v) < 1000 else f"{v:,.0f}"
    return html.escape(str(v))


def render(result: dict, ctx: Any = None, card: dict | None = None, cluster: list[str] | None = None) -> str:
    a = result["address"]
    m = result.get("metrics", {})
    rows = []
    for g in result.get("gates", []):
        cls, label = ("pass", "PASS") if g["pass"] else ("fail", "FAIL") if g["pass"] is False else ("na", "n/a")
        rows.append(f"<tr><td>{html.escape(g['gate'])}</td><td class='{cls}'>{label}</td>"
                    f"<td>{html.escape(str(g['value']))}</td><td>{html.escape(str(g['threshold']))}</td></tr>")
    ev = []
    for f in result.get("findings", []):
        if f.severity == "INFO":
            continue
        detail = "; ".join(f"{k}={_fmt(v)}" for k, v in list(f.metrics.items())[:6])
        evid = "; ".join(html.escape(str(e))[:160] for e in f.evidence[:3])
        ev.append(f"<tr><td><b>{f.code}</b></td><td class='{'fail' if f.severity == 'VETO' else 'na'}'>"
                  f"{f.severity}</td><td>{detail}</td><td>{evid}</td></tr>")
    months = ""
    mdf = m.get("months")
    if mdf is not None and getattr(mdf, "height", 0):
        months = "<table><tr><th>Month</th><th>Grade</th><th>Reasons</th></tr>" + "".join(
            f"<tr><td>{r['month']}</td><td>{r['grade']}</td><td>{html.escape(r.get('reasons') or '')}</td></tr>"
            for r in mdf.iter_rows(named=True)) + "</table>"
    curve = ""
    if ctx is not None and ctx.curve is not None and not ctx.curve.is_empty():
        idx = ctx.curve["twr_index"].to_list()
        curve = _svg_curve(idx[:: max(1, len(idx) // 450)])
    cardhtml = ""
    if card:
        cardhtml = "<table>" + "".join(f"<tr><td>{k}</td><td>{_fmt(v)}</td></tr>" for k, v in card.items()) + "</table>"
    cl = ""
    if cluster:
        cl = "<h2>Cluster members</h2><p>" + " ".join(f"<code>{c}</code>" for c in cluster) + "</p>"
    qa = " · ".join(f"<a href='{u.format(a=a)}'>{n}</a>" for u, n in zip(LINKS, ("HypurrScan", "Hyperdash", "HyperX"),
                                                                       strict=True))
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{a[:10]} dossier</title><style>{CSS}</style></head><body>
<h1>Wallet <code>{a}</code></h1>
<p><span class='tag'>stage: {result['stage']}</span><span class='tag'>category: {result['category']['category']}
(p_algo {result['category']['p_algo']:.2f})</span><span class='tag'>score: {result.get('score', '-')}</span></p>
<p>QA: {qa}</p><p class='na'>Generated {datetime.now(UTC):%Y-%m-%d %H:%M UTC}. Research tooling, not financial advice.</p>
<h2>Why this verdict</h2><p>{html.escape(', '.join(result.get('reasons', [])) or 'all gates passed')}</p>
<h2>Gates</h2><table><tr><th>Gate</th><th>Result</th><th>Value</th><th>Threshold</th></tr>{''.join(rows)}</table>
<h2>Detector findings</h2><table><tr><th>Code</th><th>Severity</th><th>Metrics</th><th>Evidence</th></tr>{''.join(ev) or '<tr><td colspan=4 class=na>none</td></tr>'}</table>
<h2>Equity curve</h2>{curve}<h2>Monthly grades</h2>{months}<h2>Copyability</h2>{cardhtml or "<p class='na'>n/a</p>"}{cl}
</body></html>"""
