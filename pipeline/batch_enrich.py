"""Enrichment through Anthropic's Message Batches API (50% price; queue held server-side).

Same agent, prompt, schema, validation, ledger and statuses as the synchronous path
(pipeline/enrich.py); only the transport differs:

  queue (DB) -> pack requests of <= 50 reviews -> group requests into jobs
  -> budget admission per job (spent + reserved + job worst case <= budget) -> submit job, save its id
  -> poll -> collect results -> validate + commit each request atomically
  -> invalid items: re-queued once (next job), then capped sync fallback, then quarantine
  -> errored/expired requests: not billed, re-queued.

Ctrl-C (or --stop-after-batches N jobs collected) leaves submitted jobs running at the
provider; the next session collects them instead of paying to resubmit.
"""
from __future__ import annotations

import json
import signal
import time
import uuid

from . import providers
from .config import DEFAULTS
from .enrich import Enricher, batch_key, build_user
from .rates import cost, worst_case

JOB_TABLE = """CREATE TABLE IF NOT EXISTS batch_jobs(batch_id TEXT PRIMARY KEY, session_id TEXT, submitted_at REAL,
  n_requests INTEGER, reserved_usd REAL, requests TEXT, status TEXT, ended_at REAL, collected_at REAL, label_config TEXT)"""


class BatchEnricher(Enricher):
    def __init__(self, *a, requests_per_job=500, max_inflight_jobs=4, poll_seconds=30, **kw):
        super().__init__(*a, **kw)
        if self.provider == "anthropic":
            self.p = providers.make("anthropic-batch", self.model, self.effort)
        elif self.provider != "mock":
            raise SystemExit("--mode batch is implemented for the Anthropic Message Batches API (or mock).")
        self.requests_per_job, self.max_inflight, self.poll = requests_per_job, max_inflight_jobs, poll_seconds
        self.store.db.execute(JOB_TABLE)

    # texts inside submitted-but-uncollected jobs are not pending (never pay twice)
    def in_flight_hashes(self):
        hs = set()
        for (req,) in self.store.db.execute("SELECT requests FROM batch_jobs WHERE collected_at IS NULL AND label_config=?", (self.config,)):
            for r in json.loads(req).values():
                hs.update(r["hashes"])
        return hs

    def queue(self):
        fl = self.in_flight_hashes()
        q = [x for x in self.pending() if x["text_hash"] not in fl]
        n_rows = dict(self.store.db.execute("SELECT text_hash, n FROM texts").fetchall())
        for x in q:
            x["n"] = n_rows[x["text_hash"]]
        return q

    def _pack(self, items, cap):
        reqs, cur, chars = [], [], 0
        for it in items:
            if cur and (len(cur) >= cap or chars + len(it["rep_text"]) > DEFAULTS["batch_char_cap"]):
                reqs.append(cur); cur, chars = [], 0
            cur.append(it); chars += len(it["rep_text"])
        if cur:
            reqs.append(cur)
        return reqs

    def _submit_job(self, reqs, spent, reserved):
        body, meta, res_total = [], {}, 0.0
        for batch in reqs:
            max_tokens = 200 + DEFAULTS["max_output_tokens_per_review"] * len(batch) + sum(len(b["rep_text"]) // 12 for b in batch)
            est_in = (len(self.system) + sum(len(b["rep_text"]) + 30 for b in batch)) // 3
            r = worst_case(self.p.name, self.model, est_in, max_tokens, self.rates)
            if spent + reserved + res_total + r > self.budget:
                break
            cid = "q" + uuid.uuid4().hex[:20]
            res_total += r
            attempt = 1 + max(b["attempts"] for b in batch)
            meta[cid] = {"rep_ids": [b["rep_id"] for b in batch], "hashes": [b["text_hash"] for b in batch], "attempt": attempt}
            if self.p.name == "mock":
                body.append({"custom_id": cid, "user": build_user(batch), "max_tokens": max_tokens})
            else:
                body.append({"custom_id": cid, "params": self.p.params(self.system, build_user(batch), self.schema, max_tokens)})
        if not body:
            return None
        if self.p.name == "mock":
            bid = "mockbatch_" + uuid.uuid4().hex[:12]
            self._mock_jobs[bid] = body
        else:
            resp = self.p.submit(body)
            bid = resp["id"]
        self.store.begin()
        self.store.db.execute("INSERT INTO batch_jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (bid, self.session, time.time(), len(body), res_total, json.dumps(meta), "submitted", None, None, self.config))
        self.store.commit()
        print(f"[batch] submitted job {bid}: {len(body)} requests / {sum(len(m['rep_ids']) for m in meta.values())} texts, "
              f"reserved ${res_total:.4f}")
        return bid

    def _results(self, bid):
        if self.p.name == "mock":
            for req in self._mock_jobs.pop(bid, []):  # mock jobs die with the process -> texts re-queued
                try:
                    r = self.p.complete(self.system, req["user"], self.schema, req["max_tokens"])
                    yield {"custom_id": req["custom_id"], "result": {"type": "succeeded", "message": {
                        "id": r.provider_request_id, "stop_reason": r.stop_reason, "content": [{"type": "text", "text": r.text}],
                        "usage": {"input_tokens": r.usage["input"], "output_tokens": r.usage["output"]}}}}
                except providers.TransportError as e:
                    yield {"custom_id": req["custom_id"], "result": {"type": "errored", "error": {"message": str(e)}}}
            return
        st = self.p.status(bid)
        yield from self.p.results(st["results_url"])

    def _ended(self, bid):
        if self.p.name == "mock":
            return True, {"processing_status": "ended"}
        st = self.p.status(bid)
        return st.get("processing_status") == "ended", st

    def _collect(self, bid, meta, submitted_at, phase, counters):
        texts = {r["text_hash"]: dict(r) for r in self.store.db.execute(
            f"SELECT text_hash, rep_id, rep_text, n FROM texts WHERE text_hash IN ({','.join('?' * sum(len(m['hashes']) for m in meta.values()))})",
            [h for m in meta.values() for h in m["hashes"]])}
        now = time.time()
        n_lines = n_err = 0
        for line in self._results(bid):
            m = meta.get(line["custom_id"])
            if not m:
                continue
            n_lines += 1
            n_err += line["result"]["type"] != "succeeded"
            batch = [texts[h] for h in m["hashes"]]
            res = line["result"]
            log = {"request_id": f"{bid}:{line['custom_id']}", "started_at": submitted_at, "ended_at": now, "attempt": m["attempt"],
                   "review_ids": m["rep_ids"], "provider": self.p.name, "model": self.model}
            parsed, err = None, None
            if res["type"] == "succeeded":
                r = providers.Anthropic.parse(res["message"])
                log.update(usage=r.usage, usage_known=True, provider_request_id=r.provider_request_id)
                if r.stop_reason in ("refusal", "max_tokens"):
                    log.update(outcome="failed", error=f"stop_reason:{r.stop_reason}"); err = f"invalid_output:{r.stop_reason}"
                else:
                    try:
                        obj = json.loads(r.text)
                        parsed = obj["results"]
                        if not isinstance(parsed, list):
                            raise ValueError("results not a list")
                        log.update(outcome="succeeded")
                    except (ValueError, KeyError, TypeError) as e:
                        log.update(outcome="failed", error=f"invalid_json:{e}"[:200]); err = "invalid_output:json"; parsed = None
            else:   # errored / expired / canceled: not billed -> back to the queue
                log.update(outcome="failed", error=f"batch_{res['type']}:{json.dumps(res.get('error', ''))[:200]}", usage={},
                           usage_known=True)
                err = f"transport_batch_{res['type']}"
            self._commit({"batch": batch, "logs": [log], "parsed": parsed, "error": err, "attempt": m["attempt"]},
                         phase, self.config, self.p, counters)
        self.store.begin()
        self.store.db.execute("UPDATE batch_jobs SET status='collected', collected_at=? WHERE batch_id=?", (time.time(), bid))
        self.store.commit()
        if n_lines and n_err == n_lines:
            print(f"[batch] every request in job {bid} errored (e.g. invalid request or key problem) - stopping; see calls log.")
            self.stop.set()
            self._all_errored = True

    def _resolve_exhausted(self, counters):
        """Texts that failed validation twice: capped synchronous fallback, else quarantine."""
        db = self.store.db
        n_distinct = db.execute("SELECT COUNT(*) FROM texts").fetchone()[0]
        fb_cap = int(self.fallback_max_fraction * n_distinct) if self.fb else 0
        fb_used = db.execute("SELECT COUNT(*) FROM calls WHERE role='enrich' AND label_config=?", (getattr(self, "fb_config", "-"),)).fetchone()[0]
        for x in [q for q in self.queue() if q["attempts"] > DEFAULTS["invalid_output_retries"]]:
            tried_fb = db.execute("SELECT 1 FROM calls WHERE role='enrich' AND label_config=? AND review_ids LIKE ?",
                                  (getattr(self, "fb_config", "-"), f'%"{x["rep_id"]}"%')).fetchone()
            if self.fb and fb_used < fb_cap and not tried_fb:
                out = self._call(self.fb, [x], 1700 + DEFAULTS["max_output_tokens_per_review"], 3)
                self._commit(out, self._phase, self.fb_config, self.fb, counters)
                fb_used += 1
                counters["fallback_calls"] += 1
                if db.execute("SELECT 1 FROM results WHERE text_hash=?", (x["text_hash"],)).fetchone():
                    continue
            if tried_fb or (self.fb and db.execute("SELECT 1 FROM calls WHERE role='enrich' AND label_config=? AND review_ids LIKE ?",
                                                    (self.fb_config, f'%"{x["rep_id"]}"%')).fetchone()):
                reason = "invalid_model_output_after_retry_and_fallback"
            else:
                reason = "invalid_model_output_after_retry" + (" (fallback cap reached)" if self.fb else " (no fallback configured)")
            self.store.begin()
            self._quarantine(x["text_hash"], reason, x["attempts"], "see calls log")
            self.store.commit()
            counters["quarantined"] += 1

    def run(self) -> dict:
        self._mock_jobs = {}
        db = self.store.db
        has_prior = db.execute("SELECT COUNT(*) FROM results WHERE label_config=?", (self.config,)).fetchone()[0] > 0
        inflight_prior = db.execute("SELECT COUNT(*) FROM batch_jobs WHERE collected_at IS NULL").fetchone()[0]
        phase = "resume" if (has_prior or inflight_prior) else "initial"
        self._phase = phase
        if phase == "resume" and not self.store.get_meta("checkpoint_before:" + self.config):
            snap = self.completed_ids()
            self.store.set_meta("checkpoint_before:" + self.config, {"saved_at": time.time(), "session": self.session, "completed_ids": snap})
            print(f"[batch] RESUME detected: saved checkpoint_before with {len(snap):,} completed IDs; {inflight_prior} job(s) to collect")
        self.store.start_session(self.session, "enrich", phase, {"mode": "batch", "label_config": self.config, "budget": self.budget,
                                                                  "requests_per_job": self.requests_per_job, "max_inflight_jobs": self.max_inflight})
        counters = dict(calls=0, failed_calls=0, spent=0.0, completed_texts=0, rows_covered=0, invalid_items=0, foreign_ids=0,
                        duplicate_ids=0, deferred=0, quarantined=0, fallback_calls=0, batches=0, jobs_submitted=0, jobs_collected=0)
        spent0 = self.store.spent()
        t0 = time.time()
        stop_reason = "queue_empty"
        old = signal.getsignal(signal.SIGINT)

        def on_sigint(sig, frm):
            print("\n[batch] Ctrl-C: stopping. Submitted jobs keep running at the provider and are collected on resume.")
            self.stop.set()
        signal.signal(signal.SIGINT, on_sigint)
        try:
            while not self.stop.is_set():
                jobs = db.execute("SELECT batch_id, requests, submitted_at, reserved_usd FROM batch_jobs WHERE collected_at IS NULL "
                                  "AND label_config=? ORDER BY submitted_at", (self.config,)).fetchall()
                for bid, req, sub_at, _ in jobs:
                    done, st = self._ended(bid)
                    if done:
                        self._collect(bid, json.loads(req), sub_at, phase, counters)
                        counters["jobs_collected"] += 1
                        el = time.time() - t0
                        print(f"[batch] collected {bid}: total +{counters['completed_texts']:,} texts ({counters['rows_covered']:,} rows) | "
                              f"session ${counters['spent']:.4f} | {el / 60:.1f} min")
                    elif st:
                        c = st.get("request_counts", {})
                        print(f"[batch] {bid}: {st.get('processing_status')} {json.dumps(c)}")
                if self.stop_after_batches is not None and counters["jobs_collected"] >= self.stop_after_batches:
                    stop_reason = "stop_after_batches (simulated interruption; uncollected jobs stay at provider)"; break
                if self.max_seconds and time.time() - t0 > self.max_seconds:
                    stop_reason = "time_cap"; break
                self._resolve_exhausted(counters)
                q = self.queue()
                if self.limit_texts:
                    q = q[: self.limit_texts]
                inflight = db.execute("SELECT COUNT(*), COALESCE(SUM(reserved_usd),0) FROM batch_jobs WHERE collected_at IS NULL "
                                      "AND label_config=?", (self.config,)).fetchone()
                n_inflight, reserved = inflight
                retry = [x for x in q if x["attempts"] >= 1]
                fresh = [x for x in q if x["attempts"] == 0]
                reqs = self._pack(retry, max(1, self.batch_size // 5)) + self._pack(fresh, self.batch_size)
                budget_blocked = False
                while reqs and n_inflight < self.max_inflight and not self.stop.is_set():
                    job = reqs[: self.requests_per_job]
                    bid = self._submit_job(job, spent0 + counters["spent"], reserved)
                    if not bid:
                        budget_blocked = True
                        break
                    taken = json.loads(db.execute("SELECT requests FROM batch_jobs WHERE batch_id=?", (bid,)).fetchone()[0])
                    reqs = reqs[len(taken):]
                    reserved += db.execute("SELECT reserved_usd FROM batch_jobs WHERE batch_id=?", (bid,)).fetchone()[0]
                    n_inflight += 1
                    counters["jobs_submitted"] += 1
                    counters["batches"] += len(taken)
                if n_inflight == 0 and not reqs:
                    stop_reason = "queue_empty"; break
                if n_inflight == 0 and budget_blocked:
                    stop_reason = f"budget_cap (spent ${spent0 + counters['spent']:.4f}, budget ${self.budget:.2f})"; break
                if self.p.name != "mock":
                    for _ in range(self.poll):
                        if self.stop.is_set():
                            break
                        time.sleep(1)
            if getattr(self, "_all_errored", False):
                stop_reason = "batch_job_all_requests_errored"
            elif self.stop.is_set() and stop_reason == "queue_empty":
                stop_reason = "interrupted_by_user (jobs continue at provider)"
        finally:
            signal.signal(signal.SIGINT, old)
        wall = time.time() - t0
        left = len(self.pending())
        summary = {"session": self.session, "mode": "batch", "phase": phase, "label_config": self.config, "stop_reason": stop_reason,
                   "wall_seconds": round(wall, 2), **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in counters.items()},
                   "spent_total_run_usd": round(spent0 + counters["spent"], 6), "pending_texts_after": left,
                   "uncollected_jobs": db.execute("SELECT COUNT(*) FROM batch_jobs WHERE collected_at IS NULL").fetchone()[0],
                   "throughput_texts_per_s": round(counters["completed_texts"] / wall, 3) if wall else None}
        self.store.end_session(self.session, summary)
        with (self.run_dir / "run_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "enrich_session", **summary}) + "\n")
        print(f"[batch] done: {stop_reason} | +{counters['completed_texts']:,} texts | calls {counters['calls']} (failed {counters['failed_calls']}) "
              f"| session ${counters['spent']:.4f} | pending {left:,} | uncollected jobs {summary['uncollected_jobs']}")
        return summary
