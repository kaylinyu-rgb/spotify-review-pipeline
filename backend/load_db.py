#!/usr/bin/env python3
"""Load a finished run's saved outputs into Postgres (no model calls).

    DATABASE_URL=postgresql://... python backend/load_db.py --run runs/full

Reads: enriched.jsonl.gz, state.sqlite (original text + verifier labels), issues.json, aggregates.csv,
topic_aggregates.csv, monthly_trends.csv, claims_all.csv, memo.json, memo_validation.json, run_summary.json,
verification_report.json, evals/golden_results.json, evals/system_tests_report.json, cost/report.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.config import load_dotenv  # noqa: E402
from pipeline.records import read_jsonl  # noqa: E402


def _csv(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _json(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    a = ap.parse_args()
    if not a.database_url:
        raise SystemExit("Set DATABASE_URL (Postgres connection string) or pass --database-url")
    import psycopg
    run = Path(a.run) if Path(a.run).is_absolute() else ROOT / a.run
    t0 = time.time()
    lite = sqlite3.connect(run / "state.sqlite")
    text = {rid: t for rid, t in lite.execute("SELECT review_id, review_text FROM source")}
    ver = {r[0]: r[1:] for r in lite.execute("SELECT review_id, topic, intent, severity FROM verify")}
    with psycopg.connect(a.database_url, autocommit=False) as con, con.cursor() as cur:
        cur.execute((ROOT / "backend" / "schema.sql").read_text())
        cols = ("review_id status reason topic issue_id intent severity sentiment evidence_quote quote_source needs_review entities "
                "cache_source_id config_id request_id rating review_ts app_version likes review_text v_topic v_intent v_severity").split()
        n = 0
        cfg_ids: dict[str, int] = {}
        with cur.copy(f"COPY reviews ({','.join(cols)}) FROM STDIN") as cp:
            for r in read_jsonl(run / "enriched.jsonl"):
                comp = r["status"] == "completed"
                v = ver.get(r["review_id"])  # only the sampled original itself was verified
                ts = r.get("x_timestamp") or None
                cp.write_row((r["review_id"], r["status"], r.get("reason"), r.get("topic"),
                              r.get("x_label") if comp and r["intent"] in ("complaint", "cancellation") else None,
                              r.get("intent"), r.get("severity"), r.get("sentiment"), r.get("evidence_quote"), r.get("x_quote_source"),
                              r.get("needs_review"), "|".join(r.get("entities") or []) or None, r.get("cache_source_id"),
                              cfg_ids.setdefault(r["label_config"], len(cfg_ids) + 1) if r.get("label_config") else None,
                              r.get("x_request_id") if not r.get("cache_source_id") else None,
                              int(r["x_rating"]) if (r.get("x_rating") or "").isdigit() else None, ts, r.get("x_app_version") or None,
                              int(r["x_likes"]) if (r.get("x_likes") or "").isdigit() else None, None if r.get("cache_source_id") else (text.get(r["review_id"]) or "")[:1000],
                              *(v if v else (None, None, None))))
                n += 1
        issues = {i["issue_id"]: i for i in json.loads((run / "issues.json").read_text())}
        for g in _csv(run / "aggregates.csv"):
            i = issues.get(g["issue_id"], {})
            cur.execute("INSERT INTO issues VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (g["issue_id"], int(g["rank"]), g["topic"], i.get("title"), i.get("description"), int(g["complaint_count"]),
                         int(g["severity_sum"]), g["mean_severity"], int(g["priority_score"]), int(g["cancellations"]),
                         int(g["severity_4_or_5"]), int(g["needs_review"]), int(g["one_star"]),
                         json.dumps(i.get("example_review_ids", [])), i.get("named_by")))
        for t in _csv(run / "topic_aggregates.csv"):
            cur.execute("INSERT INTO topics VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (t["topic"], *[int(t[k] or 0) for k in ("completed_reviews", "complaint_count", "severity_sum")],
                         t["mean_severity"] or None, *[int(t[k] or 0) for k in ("cancellations", "sev1", "sev2", "sev3", "sev4", "sev5",
                                                                                 "praise", "request", "unclear")]))
        for m in _csv(run / "monthly_trends.csv"):
            for k, v in m.items():
                if k.startswith("complaints_"):
                    cur.execute("INSERT INTO monthly VALUES (%s,%s,%s,%s,%s,%s)",
                                (m["month"], k[len("complaints_"):], int(v), int(m["rows"]), int(m["completed"]), int(m["complaints"])))
        if (run / "claims_all.csv").exists():
            for c in _csv(run / "claims_all.csv"):
                cur.execute("INSERT INTO claims VALUES (%s,%s,%s,%s,%s,%s)",
                            (c["claim_id"], c["scope"], c["issue_id"], c["metric"], c["value"], c["source"]))
        docs = {"memo": _json(run / "memo.json"), "memo_validation": _json(run / "memo_validation.json"),
                "run_summary": _json(run / "run_summary.json"), "verification": _json(run / "verification_report.json"),
                "ingestion": _json(run / "ingestion_report.json"), "totals": _json(run / "totals.json"),
                "golden": _json(ROOT / "evals" / "golden_results.json"), "system_tests": _json(ROOT / "evals" / "system_tests_report.json"),
                "cost": _json(ROOT / "cost" / "report.json"),
                "label_configs": {str(v): k for k, v in cfg_ids.items()},
                "loaded": {"run_id": run.name, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S %Z")}}
        for k, v in docs.items():
            if v is not None:
                if k == "ingestion":
                    v = {kk: vv for kk, vv in v.items() if kk != "empty_review_text_ids"} | {"empty_review_text_ids": v.get("empty_review_text_ids")}
                cur.execute("INSERT INTO docs VALUES (%s, %s)", (k, json.dumps(v, default=str)))
        cur.execute("CREATE INDEX ON reviews(issue_id); CREATE INDEX ON reviews(topic); CREATE INDEX ON reviews(intent); "
                    "CREATE INDEX ON reviews(review_ts); CREATE INDEX ON reviews(status);")
        con.commit()
        cur.execute("ANALYZE")
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        size = cur.fetchone()[0]
    print(f"[load_db] {n:,} reviews, {len(issues)} issues loaded into Postgres in {time.time() - t0:.1f}s; database size {size}")


if __name__ == "__main__":
    main()
