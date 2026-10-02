# Running 24/7

## This Mac (now)
1. `uv run python scripts/make_launchd.py` writes five plists to `deploy/launchd/` (tape, worker, monitor, scheduler, tracker).
2. Install (once you are happy): `cp deploy/launchd/com.hlscout.*.plist ~/Library/LaunchAgents/ && for f in ~/Library/LaunchAgents/com.hlscout.*.plist; do launchctl load "$f"; done`.
   Stop: `launchctl unload` the same files. Services run under `caffeinate -s` (no idle sleep on AC) and restart on failure.
3. Not done automatically (system settings): keep the Mac on AC power and set "Prevent automatic sleeping when the display is off" /
   lid-close behaviour yourself. Check `uv run hlscout health` and http://127.0.0.1:8765.
4. Secrets: `.env` (mode 600, gitignored) holds `HYPEDEXER_API_KEY`, optional `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.

## VPS later
State is files + SQLite, so migration is a copy: `rsync -a data/ .env config/ user@vps:hl-scout/`, then either
`docker build -f deploy/Dockerfile -t hlscout . && docker run -d -v $PWD/data:/app/data --env-file .env hlscout`, or install
`deploy/systemd/hlscout-*.service` as user units (`systemctl --user enable --now hlscout-tape ...`). Run exactly ONE copy of each
service against a given `data/` directory (the shared rate limiter lives in `data/ratelimit.sqlite`).
