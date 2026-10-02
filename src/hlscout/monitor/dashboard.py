"""Tiny local dashboard + /health (stdlib only, bound to 127.0.0.1)."""

from __future__ import annotations

import html
import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


TRACKER_HTML = open(__file__.replace('dashboard.py', 'tracker.html')).read()


def serve(root: Path, con_factory, port: int = 8765, deep_cap: int | None = None) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            con = con_factory()
            if self.path == "/health":
                body, ctype = json.dumps(health(root, con)), "application/json"
            elif self.path == "/progress.json":
                from hlscout.monitor.progress import snapshot

                body, ctype = json.dumps(snapshot(root, con, deep_cap=deep_cap)), "application/json"
            elif self.path.startswith("/api/"):
                from urllib.parse import parse_qs, urlparse

                from hlscout.monitor import api

                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if u.path == "/api/watchlist":
                    obj = api.watchlist(con)
                elif u.path.startswith("/api/wallet/"):
                    obj = api.wallet(con, u.path.rsplit("/", 1)[1])
                elif u.path == "/api/events":
                    obj = api.events(con, int(qs.get("since", ["0"])[0]), int(qs.get("limit", ["500"])[0]))
                else:
                    obj = None
                body, ctype = json.dumps(obj if obj is not None else {"error": "not found"}), "application/json"
            elif self.path == "/events":
                body, ctype = page(root, con), "text/html"
            else:
                body, ctype = TRACKER_HTML, "text/html"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), H)
