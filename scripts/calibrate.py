"""Run the compendium §10 calibration addresses through the pipeline and print verdicts."""
import asyncio
import sys
from pathlib import Path

from hlscout.clients.info import InfoClient
from hlscout.clients.ratelimit import RateLimiter
from hlscout.recon.vet import vet_address

CAL = {
    "P1/N4 Wintermute-labelled": "0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00",
    "N5 Abraxas-b83d": "0xb83de012dba672c76a7dbbbf3e459cb59d7d6e36",
    "P2 Abraxas-5b5d": "0x5b5d51203a0f9079f8aeb098a6523a13f298c060",
    "N1 Garrett": "0x92ea19ecEb7a8dE0f50978A1583A5D8b018050e9".lower(),
    "N2 pension-usdt": "0x0ddf9bae2af4b874b96d287a5ad42eb47138a902",
    "N3 Machi": "0x020ca66c30bec2c4fe3861a94e4db4a498a35872",
    "N10 Dexter HFT": "0xb7e0b9fbc9479330d70bcc82a7d4325a20e8d1aa",
    "337afda": "0x337afda118de433f5a8c8ad6d6ef48b76d027a06",
    "mk4_lul": "0x77375a8c9d13bf79afb2a87f1b0ac1dfd5f5bf66",
    "P3 bf73": "0xbf732ea04197942783e34730ed6e0f6099575d58",
    "P5 3b11": "0x3b11267dfc4b9ebe8427e8f557056b4b6ce98112",
    "P6 e650": "0xe6503009ee1a648c3775b6b8444afdddb786f1a9",
}
only = sys.argv[1:]


async def main():
    info = InfoClient(RateLimiter())
    for name, a in CAL.items():
        if only and not any(o in name for o in only):
            continue
        try:
            r = await vet_address(info, a, Path("data"))
        except Exception as e:  # noqa: BLE001
            print(f"{name}: ERROR {e!r}"[:200], flush=True)
            continue
        v = r["verdict"]
        print(f"{name}: fills={r['n_fills']} capped={r['fills_capped']} vetoes={v['vetoes']} "
              f"flags={v['flags']} cat={r['category']['category']}({r['category']['p_algo']:.2f}) "
              f"recon_ok={r['reconcile_ok']}", flush=True)
    await info.aclose()

asyncio.run(main())
