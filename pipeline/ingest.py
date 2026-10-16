"""Stage 1 - PREPARE (code only, no model).

Reads every row with a real CSV parser, preserves IDs and source values, hashes
each source row, profiles quality, finds exact duplicate texts, quarantines
empty texts and builds the pending-work queue (one entry per distinct text).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import statistics
import time
from collections import Counter
from pathlib import Path

from .config import ROOT, FULL_SHA256
from .sourceio import file_sha, read_rows, row_sha, text_hash
from .store import Store

QUEUE_SEED = "queue-order-v1"


def _checker():
    spec = importlib.util.spec_from_file_location("check_submission", ROOT / "tools" / "check_submission.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ingest(input_csv: Path, run_dir: Path, force: bool = False) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    store = Store(run_dir / "state.sqlite")
    fsha = file_sha(input_csv)
    prev = store.get_meta("input")
    if prev and not force:
        if prev["sha256"] != fsha:
            raise SystemExit(f"Run {run_dir.name} was ingested from a different file ({prev['sha256'][:12]}). Use a new --run id.")
        print(f"[ingest] already ingested {prev['rows']} rows (sha {fsha[:12]}); skipping.")
        return json.loads((run_dir / "ingestion_report.json").read_text())

    t0 = time.time()
    db = store.db
    store.begin()
    db.execute("DELETE FROM source"); db.execute("DELETE FROM texts")
    ids, ratings, months, app_missing = set(), Counter(), Counter(), 0
    dup_ids, empties, lengths = [], [], []
    first_seen: dict[str, str] = {}
    counts: Counter = Counter()
    invalid_rating = 0
    for idx, row in enumerate(read_rows(input_csv)):
        rid, text = row["review_id"], row["review_text"]
        if rid in ids:
            dup_ids.append(rid)
        ids.add(rid)
        empty = not text.strip()
        th = None
        if empty:
            empties.append(rid)
        else:
            th = text_hash(text)
            counts[th] += 1
            if th not in first_seen:
                first_seen[th] = rid
                db.execute("INSERT INTO texts VALUES(?,?,?,?,?)",
                           (th, rid, 0, text, hashlib.sha256(f"{QUEUE_SEED}:{th}".encode()).hexdigest()))
            lengths.append(len(text))
        if not row["app_version"].strip():
            app_missing += 1
        if row["review_rating"] not in {"1", "2", "3", "4", "5"}:
            invalid_rating += 1
        ratings[row["review_rating"]] += 1
        months[row["review_timestamp"][:7]] += 1
        db.execute("INSERT INTO source VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (idx, rid, row_sha(row), th, int(empty), text, row["review_rating"], row["review_likes"],
                    row["app_version"], row["review_timestamp"]))
    db.executemany("UPDATE texts SET n=? WHERE text_hash=?", ((n, th) for th, n in counts.items()))
    rows = idx + 1
    meta = {"path": str(input_csv), "name": Path(input_csv).name, "sha256": fsha, "bytes": Path(input_csv).stat().st_size,
            "rows": rows, "is_full_course_file": fsha == FULL_SHA256}
    store.set_meta("input", meta)
    store.commit()

    top_dups = sorted(((n, th) for th, n in counts.items() if n > 1), reverse=True)[:25]
    top = []
    for n, th in top_dups:
        r = db.execute("SELECT rep_id, rep_text FROM texts WHERE text_hash=?", (th,)).fetchone()
        top.append({"text": r["rep_text"][:80], "rows": n, "rep_review_id": r["rep_id"]})
    nonempty = rows - len(empties)
    report = {
        "input": meta,
        "records": rows,
        "unique_review_ids": len(ids),
        "duplicate_review_ids": len(dup_ids),
        "empty_review_text": len(empties),
        "empty_review_text_ids": empties,
        "nonempty_to_classify": nonempty,
        "distinct_nonempty_texts": len(counts),
        "rows_reusable_via_exact_text_cache": nonempty - len(counts),
        "missing_app_version": app_missing,
        "invalid_ratings": invalid_rating,
        "reviews_by_rating": dict(sorted(ratings.items())),
        "reviews_by_month": dict(sorted(months.items())),
        "text_length_chars": {"mean": round(statistics.mean(lengths), 2) if lengths else 0,
                              "median": statistics.median(lengths) if lengths else 0,
                              "p99": sorted(lengths)[int(.99 * (len(lengths) - 1))] if lengths else 0,
                              "max": max(lengths) if lengths else 0},
        "top_duplicate_texts": top,
        "quarantine_rule": "Rows whose review_text is empty after strip() are quarantined with reason empty_review_text. "
                           "Missing app_version alone does not block classification. No other row is filtered out.",
        "seconds": round(time.time() - t0, 2),
    }
    (run_dir / "ingestion_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    # deterministic profile produced by the provided helper (required grading/ingestion.json)
    prof = _checker().profile(input_csv)
    (run_dir / "ingestion.json").write_text(json.dumps(prof, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(f"[ingest] {rows:,} rows | {nonempty:,} nonempty | {len(counts):,} distinct texts | "
          f"{len(empties)} empty -> quarantine | {len(dup_ids)} duplicate IDs | {app_missing:,} missing app_version "
          f"| {report['seconds']}s")
    return report
