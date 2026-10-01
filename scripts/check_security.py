"""CI guard (plan §15.1): fail if any forbidden signing/execution token appears in src/."""
import pathlib
import sys

FORBIDDEN = ["Exchange(", "private_key", "approveBuilderFee", "hyperliquid-cli"]
bad = []
for p in pathlib.Path("src").rglob("*.py"):
    text = p.read_text()
    bad += [f"{p}: {tok}" for tok in FORBIDDEN if tok in text]
if bad:
    print("\n".join(bad))
    sys.exit(1)
print("security check ok")
