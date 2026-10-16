"""Read-only progress report (no model calls)."""
from __future__ import annotations

from pathlib import Path

from .config import label_config
from .store import Store


def status(run_dir: Path, enrich_cfg):
    s = Store(run_dir / "state.sqlite")
    db = s.db
    cfg = label_config(*enrich_cfg)
    inp = s.get_meta("input") or {}
    rows = db.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    distinct = db.execute("SELECT COUNT(*) FROM texts").fetchone()[0]
    done = db.execute("SELECT COUNT(*) FROM results WHERE label_config=?", (cfg,)).fetchone()[0]
    done_any = db.execute("SELECT COUNT(DISTINCT text_hash) FROM results").fetchone()[0]
    q = db.execute("SELECT reason, COUNT(*) FROM quarantine GROUP BY 1").fetchall()
    covered = db.execute("SELECT COUNT(*) FROM source s WHERE EXISTS (SELECT 1 FROM results r WHERE r.text_hash=s.text_hash)").fetchone()[0]
    calls = db.execute("SELECT role, COUNT(*), SUM(outcome='failed'), ROUND(SUM(cost_usd),4) FROM calls GROUP BY role").fetchall()
    print(f"run {run_dir.name}: input {inp.get('name')} ({rows:,} rows, {distinct:,} distinct texts)")
    print(f"  label_config {cfg}: {done:,} distinct texts done ({done_any:,} any config) -> {covered:,} rows covered")
    print(f"  quarantined distinct texts: {dict((r[0], r[1]) for r in q) or 0}")
    for r in calls:
        print(f"  calls {r[0]:<7} n={r[1]:<7} failed={r[2]:<5} cost=${r[3]}")
    print(f"  total known spend ${s.spent():.4f}")
