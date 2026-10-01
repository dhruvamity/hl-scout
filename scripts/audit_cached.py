"""Re-run detectors on already-hydrated addresses (no network)."""
import sys
from pathlib import Path

from hlscout.recon.vet import audit, load_raw

sys.path.insert(0, "scripts")
for a in sys.argv[1:] or [p.stem for p in Path("data/raw/fills").glob("*.parquet")]:
    r = audit(a, load_raw(Path("data"), a)); v = r["verdict"]
    print(a[:10], f"fills={r['n_fills']} twr={r['twr']:.2f} dd={r['max_dd_twr']:.2f} sharpe={r['sharpe']:.1f}",
          "V:", v["vetoes"], "F:", v["flags"], r["category"]["category"])
