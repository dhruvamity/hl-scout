from hlscout.config import load_config
from hlscout.storage import connect_state


def test_state_wal(tmp_path):
    con = connect_state(tmp_path)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.execute("INSERT INTO addresses(address) VALUES ('0xabc')")


def test_default_config(tmp_path):
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.gates.max_dd_twr == 0.30 and cfg.api.weight_per_min == 1200
