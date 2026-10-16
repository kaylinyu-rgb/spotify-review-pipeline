"""Standardized grading/ export (code only) + run_summary.json / data_manifest.json."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from .config import FULL_ROWS, FULL_SHA256, ROOT
from .records import configs, grading_view, read_jsonl, write_jsonl_gz
from .store import Store


def _git_rev():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "uncommitted"


def call_rows(store: Store):
    for c in store.db.execute("SELECT * FROM calls ORDER BY started_at, request_id"):
        if c["role"] not in ("enrich", "verify", "group", "memo"):
            continue
        yield {"request_id": c["request_id"], "role": c["role"], "review_ids": json.loads(c["review_ids"]),
               "model": c["model"], "phase": c["phase"] if c["role"] == "enrich" else c["role"], "outcome": c["outcome"],
               "label_config": c["label_config"],
               "input_tokens": int((c["input_tokens"] or 0) + (c["cached_input_tokens"] or 0) + (c["cache_write_tokens"] or 0)),
               "output_tokens": int(c["output_tokens"] or 0),
               "uncached_input_tokens": c["input_tokens"] or 0, "cached_input_tokens": c["cached_input_tokens"] or 0,
               "cache_write_tokens": c["cache_write_tokens"] or 0, "usage_known": bool(c["usage_known"]),
               "cost_usd": c["cost_usd"], "provider": c["provider"], "provider_request_id": c["provider_request_id"],
               "error": c["error"], "attempt": c["attempt"], "session_id": c["session_id"],
               "started_at": c["started_at"], "duration_s": c["duration_s"]}


def export(run_dir: Path, enrich_cfg, out: Path | None = None, allow_mock: bool = False) -> dict:
    out = out or run_dir / "grading"
    primary, fb = configs(enrich_cfg)
    if primary.startswith("mock:") and not allow_mock:
        raise SystemExit("Refusing to export mock (synthetic) labels as a grading folder. Use --allow-mock for tests only.")
    store = Store(run_dir / "state.sqlite")
    inp = store.get_meta("input")
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("records.jsonl", "calls.jsonl"):
        (out / stale).unlink(missing_ok=True)
    recs = list(read_jsonl(run_dir / "enriched.jsonl"))
    n = write_jsonl_gz(out / "records.jsonl.gz", (grading_view(r) for r in recs))
    calls = list(call_rows(store))
    write_jsonl_gz(out / "calls.jsonl.gz", calls)
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        if (run_dir / name).exists():
            shutil.copy(run_dir / name, out / name)
    shutil.copy(run_dir / "ingestion.json", out / "ingestion.json")
    run = {"version": "a5-audit-v1", "analysis_count": inp["rows"], "analysis_sha256": inp["sha256"],
           "classification_input_fields": ["review_text"], "allow_multi_issue": False}
    (out / "run.json").write_text(json.dumps(run) + "\n")
    before = store.get_meta("checkpoint_before:" + primary)
    completed = [r["review_id"] for r in recs if r["status"] == "completed"]
    if before:
        (out / "checkpoint_before.json").write_text(json.dumps({"completed_ids": before["completed_ids"],
                                                                "saved_at": before["saved_at"], "session": before["session"]}) + "\n")
        (out / "checkpoint_after.json").write_text(json.dumps({"completed_ids": completed, "saved_at": time.time()}) + "\n")
    # ---- run summary + manifest
    db = store.db
    by_role = {r["role"]: dict(r) for r in db.execute(
        "SELECT role, COUNT(*) calls, SUM(outcome='failed') failed, SUM(input_tokens) input_tokens, SUM(cached_input_tokens) cached, "
        "SUM(cache_write_tokens) cache_write, SUM(output_tokens) output_tokens, SUM(cost_usd) cost_usd, "
        "SUM(usage_known=0) usage_unknown_calls, SUM(duration_s) summed_call_seconds FROM calls GROUP BY role")}
    sessions = [dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY started_at")]
    st = {k: sum(1 for r in recs if r["status"] == k) for k in ("completed", "quarantined")}
    reasons = {}
    for r in recs:
        if r["status"] == "quarantined":
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    summary = {"run_id": run_dir.name, "input": inp, "is_full_course_file": inp["sha256"] == FULL_SHA256 and inp["rows"] == FULL_ROWS,
               "label_config": primary, "fallback_label_config": fb, "code_version": _git_rev(), "records": n, **st,
               "quarantine_reasons": reasons, "cache_reuse_rows": sum(1 for r in recs if "cache_source_id" in r),
               "calls_by_role": by_role, "total_cost_usd_known": round(sum((v["cost_usd"] or 0) for v in by_role.values()), 6),
               "enrich_sessions": [{k: s[k] for k in ("session_id", "phase", "started_at", "ended_at")} | json.loads(s["summary"] or "{}")
                                   for s in sessions if s["stage"] == "enrich"],
               "checkpoint_before_ids": len(before["completed_ids"]) if before else 0, "checkpoint_after_ids": len(completed),
               "budget_rule": "<= $10 per 100k input rows unless --budget is given; spent+reserved+next worst-case <= budget"}
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    files = {}
    for p in sorted(list(run_dir.glob("*.*")) + list(out.glob("*.*"))):
        if p.is_file() and p.suffix in (".json", ".csv", ".gz", ".md", ".jsonl"):
            files[str(p.relative_to(run_dir))] = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {"run_id": run_dir.name, "source": inp, "code_version": _git_rev(), "label_config": primary,
                "prompts": sorted(p.name for p in (ROOT / "pipeline" / "prompts").glob("*.md")),
                "prompt_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "pipeline" / "prompts").glob("*.md")},
                "outputs_sha256": files}
    (run_dir / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[export] {out}: {n:,} records ({st['completed']:,} completed, {st['quarantined']:,} quarantined), {len(calls)} calls, "
          f"checkpoints {'yes' if before else 'NO (no resume session yet)'}")
    return summary
