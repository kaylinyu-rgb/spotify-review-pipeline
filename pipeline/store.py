"""Run state in SQLite: the queue, the result cache, statuses, the call log and the spend ledger.

A single writer (the orchestrator thread) commits after every batch inside one
transaction, so a crash or Ctrl-C can lose at most the in-flight batches, never
half-written or double-counted results.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS source(
  row_idx INTEGER PRIMARY KEY, review_id TEXT UNIQUE NOT NULL, source_sha TEXT NOT NULL,
  text_hash TEXT, is_empty INTEGER NOT NULL, review_text TEXT NOT NULL, review_rating TEXT,
  review_likes TEXT, app_version TEXT, review_timestamp TEXT);
CREATE INDEX IF NOT EXISTS source_text ON source(text_hash);
-- one row per distinct nonempty text; rep_id = first occurrence in file order (gets the model call)
CREATE TABLE IF NOT EXISTS texts(text_hash TEXT PRIMARY KEY, rep_id TEXT NOT NULL, n INTEGER NOT NULL,
  rep_text TEXT NOT NULL, queue_key TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS texts_queue ON texts(queue_key);
-- result cache, keyed by exact text + label_config
CREATE TABLE IF NOT EXISTS results(
  text_hash TEXT NOT NULL, label_config TEXT NOT NULL, origin_id TEXT NOT NULL,
  label TEXT NOT NULL, topic TEXT NOT NULL, intent TEXT NOT NULL, severity INTEGER NOT NULL,
  sentiment REAL NOT NULL, evidence_quote TEXT NOT NULL, quote_source TEXT NOT NULL,
  needs_review INTEGER NOT NULL, review_reason TEXT, entities TEXT NOT NULL,
  request_id TEXT NOT NULL, phase TEXT NOT NULL, session_id TEXT NOT NULL, completed_at REAL NOT NULL,
  PRIMARY KEY(text_hash, label_config));
CREATE TABLE IF NOT EXISTS attempts(text_hash TEXT NOT NULL, label_config TEXT NOT NULL, n INTEGER NOT NULL,
  last_error TEXT, PRIMARY KEY(text_hash, label_config));
CREATE TABLE IF NOT EXISTS quarantine(text_hash TEXT NOT NULL, label_config TEXT NOT NULL, reason TEXT NOT NULL,
  attempts INTEGER NOT NULL, detail TEXT, PRIMARY KEY(text_hash, label_config));
CREATE TABLE IF NOT EXISTS calls(
  request_id TEXT PRIMARY KEY, role TEXT NOT NULL, review_ids TEXT NOT NULL, model TEXT NOT NULL,
  provider TEXT NOT NULL, label_config TEXT, phase TEXT, outcome TEXT NOT NULL, error TEXT,
  input_tokens INTEGER, cached_input_tokens INTEGER, cache_write_tokens INTEGER, output_tokens INTEGER,
  usage_known INTEGER NOT NULL, cost_usd REAL, started_at REAL, ended_at REAL, duration_s REAL,
  attempt INTEGER, session_id TEXT, settings TEXT, provider_request_id TEXT);
CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY, stage TEXT, phase TEXT, started_at REAL,
  ended_at REAL, args TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS ledger(key TEXT PRIMARY KEY, value REAL);
CREATE TABLE IF NOT EXISTS verify(review_id TEXT PRIMARY KEY, text_hash TEXT, verifier TEXT, topic TEXT,
  intent TEXT, severity INTEGER, raw TEXT, request_id TEXT);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=60, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # -- meta / ledger ---------------------------------------------------------
    def get_meta(self, key, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, json.dumps(value)))

    def spent(self) -> float:
        r = self.db.execute("SELECT COALESCE(SUM(cost_usd),0) FROM calls").fetchone()
        return float(r[0])

    # -- transactions ------------------------------------------------------------
    def begin(self):
        self.db.execute("BEGIN IMMEDIATE")

    def commit(self):
        self.db.execute("COMMIT")

    def log_call(self, c: dict):
        cols = ("request_id", "role", "review_ids", "model", "provider", "label_config", "phase", "outcome", "error",
                "input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens", "usage_known", "cost_usd",
                "started_at", "ended_at", "duration_s", "attempt", "session_id", "settings", "provider_request_id")
        vals = [c.get(k) for k in cols]
        vals[2] = json.dumps(c.get("review_ids", []))
        vals[20] = json.dumps(c.get("settings", {}))
        self.db.execute(f"INSERT INTO calls({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)

    def start_session(self, session_id, stage, phase, args):
        self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                        (session_id, stage, phase, time.time(), None, json.dumps(args), None))

    def end_session(self, session_id, summary):
        self.db.execute("UPDATE sessions SET ended_at=?, summary=? WHERE session_id=?",
                        (time.time(), json.dumps(summary), session_id))
