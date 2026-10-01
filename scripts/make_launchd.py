"""Generate launchd LaunchAgent plists for tape/worker/monitor/scheduler under deploy/launchd/.

Nothing is installed automatically. To install:
    cp deploy/launchd/*.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.hlscout.*.plist
Each job runs under `caffeinate -s` (no idle sleep on AC) and restarts on failure.
"""

import plistlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "launchd"
UV = shutil.which("uv") or "uv"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)
    for name in ("tape", "worker", "monitor", "scheduler"):
        plist = {
            "Label": f"com.hlscout.{name}",
            "ProgramArguments": ["/usr/bin/caffeinate", "-s", UV, "run", "hlscout", name],
            "WorkingDirectory": str(ROOT),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 30,
            "ProcessType": "Background",
            "StandardOutPath": str(ROOT / "data" / f"{name}.log"),
            "StandardErrorPath": str(ROOT / "data" / f"{name}.err.log"),
            "EnvironmentVariables": {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"},
        }
        (OUT / f"com.hlscout.{name}.plist").write_bytes(plistlib.dumps(plist))
    print(f"wrote 4 plists to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
