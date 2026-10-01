"""Tiny local dashboard + /health (stdlib only, bound to 127.0.0.1)."""

from __future__ import annotations

import html
import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def health(root: Path, con: sqlite3.Connection) -> dict:
    now = time.time()
    hb = Path(root) / "monitor.heartbeat"
    tape = max((p.stat().st_mtime for p in Path(root).glob("tape/date=*/hour=*/*.parquet")), default=0)
    q = dict(con.execute("SELECT state, COUNT(*) FROM queue GROUP BY 1").fetchall())
    last_done = con.execute("SELECT MAX(updated_at) FROM queue WHERE state='done'").fetchone()[0]
    return {
        "monitor_age_s": now - float(hb.read_text()) if hb.exists() else None,
        "tape_age_s": now - tape if tape else None, "queue": q, "last_done": last_done,
        "tape_ok": bool(tape) and now - tape < 3 * 3600,  # files flush hourly
    }


def page(root: Path, con: sqlite3.Connection) -> str:
    rows = con.execute("SELECT e.address, e.event, e.coin, e.notional, e.ts FROM watch_events e "
                       "ORDER BY ts DESC LIMIT 50").fetchall()
    wl = con.execute("SELECT s.entity, s.category, s.score, s.stage FROM scores s WHERE s.stage IN "
                     "('qualified','needs_qa','reformed') ORDER BY s.score DESC").fetchall()
    td = lambda r: "".join(f"<td>{html.escape(str(x))}</td>" for x in r)
    return ("<html><body><h2>HL-Scout</h2><h3>Watchlist</h3><table border=1>"
            + "".join(f"<tr>{td(r)}</tr>" for r in wl) + "</table><h3>Recent events</h3><table border=1>"
            + "".join(f"<tr>{td(r)}</tr>" for r in rows) + "</table></body></html>")


def serve(root: Path, con_factory, port: int = 8765) -> HTTPServer:
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            con = con_factory()
            body = json.dumps(health(root, con)) if self.path == "/health" else page(root, con)
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if self.path == "/health" else "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a) -> None:
            pass

    return HTTPServer(("127.0.0.1", port), H)
