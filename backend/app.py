"""Dashboard backend: FastAPI over Postgres. Read-only; never calls a model.

    DATABASE_URL=postgresql://... uvicorn backend.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger("uvicorn.error")
DB = (os.environ.get("DATABASE_URL") or "").strip().strip('"').strip("'")
STATIC = Path(__file__).resolve().parent / "static"
pool = None
DB_ERROR = None
if not DB:
    DB_ERROR = "DATABASE_URL is not set on the server"
else:
    try:
        _u = urlsplit(DB)
        log.info("database host=%s port=%s db=%s user=%s", _u.hostname, _u.port, _u.path, (_u.username or "")[:12])
    except ValueError as e:
        DB_ERROR = f"DATABASE_URL could not be parsed: {e}"
    if not DB_ERROR:
        # Fail fast instead of hanging: 10 s connect timeout, 15 s wait for a pooled connection.
        pool = ConnectionPool(DB, min_size=1, max_size=int(os.environ.get("DB_POOL_MAX", "4")), timeout=15,
                              kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 10},
                              open=False)
        try:
            pool.open(wait=True, timeout=20)
            log.info("database pool ready")
        except Exception as e:  # keep serving so the error is visible instead of a silent timeout
            DB_ERROR = f"could not connect to the database: {type(e).__name__}: {e}"
            log.error(DB_ERROR)

app = FastAPI(title="Spotify review insight API", version="1.0",
              description="Serves the saved, processed review pipeline outputs from Postgres. No model calls.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["GET"])


def q(sql, args=(), one=False):
    if pool is None:
        raise HTTPException(503, DB_ERROR or "database unavailable")
    with pool.connection() as con, con.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone() if one else cur.fetchall()


def doc(key):
    r = q("SELECT value FROM docs WHERE key=%s", (key,), one=True)
    return r["value"] if r else None


@app.get("/api/ping")
def ping():
    """Liveness for the host's health check: never touches the database."""
    return {"ok": True, "db_error": DB_ERROR}


@app.get("/api/health")
def health():
    """Readiness: confirms the backend can read the processed data from Postgres."""
    if DB_ERROR:
        raise HTTPException(503, DB_ERROR)
    r = q("SELECT reltuples::bigint AS approx FROM pg_class WHERE relname='reviews'", one=True)
    exact = q("SELECT COUNT(*) AS n FROM reviews", one=True)
    return {"ok": True, "reviews_in_db": exact["n"], "approx": r["approx"] if r else None, "loaded": doc("loaded")}


@app.get("/api/overview")
def overview():
    counts = q("""SELECT COUNT(*) rows, COUNT(*) FILTER (WHERE status='completed') completed,
                  COUNT(*) FILTER (WHERE status='quarantined') quarantined,
                  COUNT(*) FILTER (WHERE reason='empty_review_text') empty_text,
                  COUNT(*) FILTER (WHERE cache_source_id IS NOT NULL) cache_reuse,
                  COUNT(*) FILTER (WHERE intent IN ('complaint','cancellation')) complaints,
                  COUNT(*) FILTER (WHERE intent='cancellation') cancellations,
                  COUNT(*) FILTER (WHERE needs_review) needs_review,
                  MIN(review_ts) first_review, MAX(review_ts) last_review FROM reviews""", one=True)
    intents = q("SELECT intent, COUNT(*) n FROM reviews WHERE status='completed' GROUP BY 1 ORDER BY 2 DESC")
    quarantine = q("SELECT reason, COUNT(*) n FROM reviews WHERE status='quarantined' GROUP BY 1 ORDER BY 2 DESC")
    rs = doc("run_summary") or {}
    ver = doc("verification") or {}
    gold = doc("golden") or {}
    cost = doc("cost") or {}
    return {"counts": counts, "intents": intents, "quarantine": quarantine,
            "run": {k: rs.get(k) for k in ("run_id", "label_config", "fallback_label_config", "is_full_course_file",
                                           "total_cost_usd_known", "calls_by_role", "checkpoint_before_ids", "checkpoint_after_ids", "input")},
            "verification": {k: ver.get(k) for k in ("verifier", "verified", "topic_agreement", "intent_agreement", "severity_exact",
                                                     "severity_mae", "disagreements", "declared_sample")},
            "golden": {k: gold.get(k) for k in ("n", "agreement", "severity_mae", "macro_f1", "ambiguous_cases")} if gold else None,
            "cost": {"pilot": (cost.get("measured") or {}).get("cold", {}).get("api_usd"),
                     "projection": (cost.get("projection") or {}).get("scenarios")} if cost else None,
            "loaded": doc("loaded")}


@app.get("/api/ranking")
def ranking(limit: int = Query(100, le=500)):
    return q("SELECT * FROM issues ORDER BY rank LIMIT %s", (limit,))


@app.get("/api/topics")
def topics():
    return q("SELECT * FROM topics ORDER BY severity_sum DESC")


@app.get("/api/trends")
def trends():
    return q("SELECT * FROM monthly ORDER BY month, topic")


@app.get("/api/recommendation")
def recommendation():
    memo = doc("memo")
    if not memo:
        raise HTTPException(404, "No memo loaded")
    claims = q("SELECT * FROM claims ORDER BY scope, length(claim_id), claim_id")
    ids = sorted({r for a in memo.get("actions", []) for r in a.get("review_ids", [])})
    ev = q("SELECT review_id, issue_id, topic, intent, severity, evidence_quote, review_ts, rating FROM reviews WHERE review_id = ANY(%s)", (ids,)) if ids else []
    return {"memo": memo, "validation": doc("memo_validation"), "claims": claims, "evidence": ev}


@app.get("/api/issues/{issue_id}")
def issue(issue_id: str):
    i = q("SELECT * FROM issues WHERE issue_id=%s", (issue_id,), one=True)
    if not i:
        raise HTTPException(404, "unknown issue")
    sev = q("SELECT severity, COUNT(*) n FROM reviews WHERE issue_id=%s GROUP BY 1 ORDER BY 1", (issue_id,))
    month = q("SELECT to_char(review_ts,'YYYY-MM') AS month, COUNT(*) AS n FROM reviews WHERE issue_id=%s GROUP BY 1 ORDER BY 1", (issue_id,))
    ex = i["example_review_ids"] or []
    examples = q("SELECT review_id, intent, severity, evidence_quote, review_ts, rating FROM reviews WHERE review_id = ANY(%s)", (ex,)) if ex else []
    claims = q("SELECT * FROM claims WHERE issue_id=%s ORDER BY length(claim_id), claim_id", (issue_id,))
    return {"issue": i, "severity_distribution": sev, "monthly": month, "examples": examples, "claims": claims}


@app.get("/api/reviews")
def reviews(issue_id: str | None = None, topic: str | None = None, intent: str | None = None, severity: int | None = None,
            status: str | None = None, needs_review: bool | None = None, verified: bool | None = None,
            q_text: str | None = Query(None, alias="q", max_length=100), limit: int = Query(25, le=100), offset: int = Query(0, ge=0)):
    where, args = [], []
    for col, val in (("issue_id", issue_id), ("topic", topic), ("intent", intent), ("severity", severity), ("status", status),
                     ("needs_review", needs_review)):
        if val is not None and val != "":
            where.append(f"{col} = %s"); args.append(val)
    if verified:
        where.append("v_topic IS NOT NULL")
    if q_text:
        where.append("review_text ILIKE %s"); args.append(f"%{q_text}%")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = q(f"SELECT COUNT(*) n FROM reviews {w}", args, one=True)["n"] if (where and not q_text) or (q_text and len(q_text) >= 3) else None
    rows = q(f"""SELECT review_id, status, reason, topic, issue_id, intent, severity, sentiment, evidence_quote, needs_review,
                 cache_source_id, rating, review_ts, v_topic, v_intent, v_severity
                 FROM reviews {w} ORDER BY severity DESC NULLS LAST, likes DESC NULLS LAST, review_id LIMIT %s OFFSET %s""",
             args + [limit, offset])
    return {"total": total, "rows": rows}


@app.get("/api/reviews/{review_id}")
def trace(review_id: str):
    """One review traced: source -> enrichment -> verification -> issue membership -> ranking -> memo claims."""
    r = q("SELECT * FROM reviews WHERE review_id=%s", (review_id,), one=True)
    if not r:
        raise HTTPException(404, "unknown review_id")
    r["label_config"] = (doc("label_configs") or {}).get(str(r.pop("config_id", None)))
    out = {"review": r, "issue": None, "claims": [], "cited_in_memo": False, "cache_source": None}
    if r["cache_source_id"]:
        out["cache_source"] = q("SELECT review_id, request_id, review_text FROM reviews WHERE review_id=%s", (r["cache_source_id"],), one=True)
        r["review_text"] = out["cache_source"]["review_text"] if out["cache_source"] else None  # identical text stored once
    if r["issue_id"]:
        out["issue"] = q("SELECT issue_id, rank, title, complaint_count, severity_sum, mean_severity, priority_score FROM issues WHERE issue_id=%s",
                         (r["issue_id"],), one=True)
        out["claims"] = q("SELECT * FROM claims WHERE issue_id=%s ORDER BY length(claim_id), claim_id", (r["issue_id"],))
    memo = doc("memo") or {}
    out["cited_in_memo"] = any(review_id in a.get("review_ids", []) for a in memo.get("actions", []))
    return out


@app.get("/api/evals")
def evals():
    return {"verification": doc("verification"), "golden": doc("golden"), "system_tests": doc("system_tests"),
            "ingestion": doc("ingestion"), "cost": doc("cost")}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
