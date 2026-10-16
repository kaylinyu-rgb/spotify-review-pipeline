"""Final per-source-ID records (code only): exactly one completed or quarantined row per source ID."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from .config import label_config, DEFAULTS
from .store import Store


def configs(enrich_cfg):
    prov, model, effort = enrich_cfg
    primary = label_config(prov, model, effort)
    fb = label_config(DEFAULTS["fallback_provider"], DEFAULTS["fallback_model"], DEFAULTS["fallback_effort"]) if prov != "mock" else primary
    return primary, fb


def build_records(run_dir: Path, enrich_cfg):
    """Yield one dict per source row in file order. Rich fields are prefixed with x_ (not part of the grading schema)."""
    db = Store(run_dir / "state.sqlite").db
    primary, fb = configs(enrich_cfg)
    res = {}
    for r in db.execute("SELECT * FROM results WHERE label_config IN (?,?) ORDER BY label_config=? ", (primary, fb, primary)):
        res[r["text_hash"]] = dict(r)   # primary overwrites fallback (ordered last)
    quar = {r["text_hash"]: dict(r) for r in db.execute("SELECT * FROM quarantine WHERE label_config=?", (primary,))}
    attempts = {r["text_hash"]: r["n"] for r in db.execute("SELECT text_hash, n FROM attempts WHERE label_config=?", (primary,))}
    for s in db.execute("SELECT * FROM source ORDER BY row_idx"):
        base = {"review_id": s["review_id"], "source_sha256": s["source_sha"]}
        meta = {"x_rating": s["review_rating"], "x_timestamp": s["review_timestamp"], "x_app_version": s["app_version"],
                "x_likes": s["review_likes"]}
        if s["is_empty"]:
            yield {**base, "status": "quarantined", "reason": "empty_review_text", "x_attempts": 0, **meta}
            continue
        r = res.get(s["text_hash"])
        if r:
            rec = {**base, "status": "completed", "topic": r["topic"], "intent": r["intent"], "sentiment": r["sentiment"],
                   "severity": r["severity"], "entities": json.loads(r["entities"]), "evidence_quote": r["evidence_quote"],
                   "needs_review": bool(r["needs_review"]), "label_config": r["label_config"]}
            if r["origin_id"] != s["review_id"]:
                rec["cache_source_id"] = r["origin_id"]   # direct original with model-call evidence
            rec.update({"x_label": r["label"], "x_subtopic": r["label"].split(".", 1)[1], "x_quote_source": r["quote_source"],
                        "x_review_reason": r["review_reason"], "x_request_id": r["request_id"], "x_phase": r["phase"], **meta})
            yield rec
        elif s["text_hash"] in quar:
            q = quar[s["text_hash"]]
            yield {**base, "status": "quarantined", "reason": q["reason"], "x_detail": q["detail"], "x_attempts": q["attempts"], **meta}
        else:
            yield {**base, "status": "quarantined", "reason": "pending_not_classified_run_incomplete",
                   "x_attempts": attempts.get(s["text_hash"], 0), **meta}


def grading_view(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("x_")}


def open_jsonl(path: Path):
    path = Path(path)
    if path.exists():
        return path.open(encoding="utf-8")
    gz = path.with_name(path.name + ".gz")
    return gzip.open(gz, "rt", encoding="utf-8")


def read_jsonl(path: Path):
    with open_jsonl(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_jsonl_gz(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n
