"""Stage 2 - CLASSIFY / ENRICH (model role: enrichment agent; code: queue, validation, ledger).

Orchestration (all code):
  pending queue (distinct texts without a cached result under this label_config)
  -> pack batches (<= 50 reviews, <= char cap)
  -> admission control: spent + reserved + next worst-case reservation <= budget
  -> shared rate limiter -> worker threads call the model (bounded transport retries w/ backoff+jitter)
  -> orchestrator thread validates every returned ID/field/quote and commits the batch atomically
  -> invalid/missing items: retry once, then capped stronger-model fallback, then quarantine.
"""
from __future__ import annotations

import json
import random
import signal
import threading
import time
import uuid
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from . import providers
from .config import DEFAULTS, INTENTS, LABELS, SEVERITIES, label_config, read_prompt, topic_of, ENRICH_PROMPT_VERSION
from .entities import extract_entities, repair_quote
from .rates import cost, load_rates, worst_case
from .store import Store


def enrich_schema():
    item = {"type": "object", "additionalProperties": False,
            "required": ["k", "label", "intent", "sev", "sent", "quote", "flag"],
            "properties": {"k": {"type": "string"}, "label": {"type": "string", "enum": list(LABELS)},
                           "intent": {"type": "string", "enum": list(INTENTS)},
                           "sev": {"type": "integer", "enum": list(SEVERITIES)},
                           "sent": {"type": "number", "enum": [-1, -0.5, 0, 0.5, 1]},
                           "quote": {"type": "string"}, "flag": {"type": "boolean"}}}
    return {"type": "object", "additionalProperties": False, "required": ["results"],
            "properties": {"results": {"type": "array", "items": item}}}


def batch_key(i: int) -> str:
    return f"r{i + 1:02d}"


def build_user(batch) -> str:
    """Reviews are sent with short per-request keys (r01..r50) instead of 36-char IDs to cut output
    tokens; code maps keys back to source review_ids and rejects missing/foreign/duplicate keys."""
    return "Label these reviews. Return one result per key.\n" + json.dumps(
        [{"k": batch_key(i), "text": b["rep_text"]} for i, b in enumerate(batch)], ensure_ascii=False)


def system_prompt():
    return read_prompt(f"{ENRICH_PROMPT_VERSION}.md").replace("{LABELS}", ", ".join(LABELS))


class Limiter:
    """Shared requests/tokens-per-minute limiter for all workers."""

    def __init__(self, rpm: int, tpm: int):
        self.rpm, self.tpm, self.lock, self.events = rpm, tpm, threading.Lock(), deque()

    def acquire(self, tokens: int):
        while True:
            with self.lock:
                now = time.time()
                while self.events and now - self.events[0][0] > 60:
                    self.events.popleft()
                used = sum(t for _, t in self.events)
                if len(self.events) < self.rpm and used + tokens <= self.tpm:
                    self.events.append((now, tokens))
                    return
            time.sleep(0.25)


def validate_item(it: dict, text: str):
    """Code-side validation of one returned record. Returns (record, None) or (None, error)."""
    try:
        label, intent, sev, sent = it["label"], it["intent"], it["sev"], it["sent"]
    except (KeyError, TypeError):
        return None, "missing_keys"
    if isinstance(label, str):
        label = label.strip().lower()
    if label not in LABELS:
        return None, f"bad_label:{label}"
    if isinstance(intent, str):
        intent = intent.strip().lower()
    if intent not in INTENTS:
        return None, f"bad_intent:{intent}"
    if type(sev) is float and sev.is_integer():
        sev = int(sev)
    if type(sev) is not int or sev not in SEVERITIES:
        return None, f"bad_severity:{sev}"
    if type(sent) not in (int, float) or not -1 <= sent <= 1:
        return None, f"bad_sentiment:{sent}"
    flag = it.get("flag")
    if type(flag) is not bool:
        return None, "bad_flag"
    quote, how = repair_quote(it.get("quote", ""), text)
    if quote is None:
        return None, "unsupported_quote"
    reasons = []
    if flag:
        reasons.append("model_flag")
    if how == "fallback_full_text":
        reasons.append("model_quote_not_in_text_replaced_by_full_text")
    return {"label": label, "topic": topic_of(label), "intent": intent, "severity": sev,
            "sentiment": round(float(sent), 3), "evidence_quote": quote, "quote_source": how,
            "needs_review": bool(reasons), "review_reason": ";".join(reasons) or None,
            "entities": extract_entities(text)}, None


class Enricher:
    def __init__(self, run_dir: Path, provider: str, model: str, effort: str, workers: int, budget: float,
                 batch_size: int, rates_path=None, max_minutes: float | None = None, stop_after_batches: int | None = None,
                 limit_texts: int | None = None, fallback_provider: str | None = None, fallback_model: str | None = None,
                 fallback_max_fraction: float = DEFAULTS["fallback_max_fraction"], fallback_effort: str | None = None, rpm: int = 400, tpm: int = 1_500_000,
                 mock_fail_rate: float = 0.0, quiet: bool = False):
        assert 1 <= batch_size <= 50, "grading contract: at most 50 reviews per enrichment request"
        self.store = Store(run_dir / "state.sqlite")
        self.run_dir = run_dir
        self.p = providers.make(provider, model, effort, mock_fail_rate=mock_fail_rate)
        self.provider, self.model, self.effort = provider, model, effort
        self.config = label_config(provider, model, effort)
        self.fb = None
        if fallback_provider and fallback_model and fallback_max_fraction > 0:
            self.fb = providers.make(fallback_provider, fallback_model, fallback_effort or DEFAULTS["fallback_effort"],
                                     mock_fail_rate=0.0)
            self.fb_config = label_config(fallback_provider, fallback_model, self.fb.effort)
        self.fallback_max_fraction = fallback_max_fraction
        self.workers, self.budget, self.batch_size = workers, budget, batch_size
        self.rates = load_rates(rates_path) if rates_path else load_rates()
        self.max_seconds = max_minutes * 60 if max_minutes else None
        self.stop_after_batches, self.limit_texts = stop_after_batches, limit_texts
        self.limiter = Limiter(rpm, tpm)
        self.system = system_prompt()
        self.schema = enrich_schema()
        self.stop = threading.Event()
        self.quiet = quiet
        self.session = "s-" + time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]

    # ------------------------------------------------------------------ queue
    def pending(self):
        db = self.store.db
        cfgs = (self.config, self.fb_config if self.fb else self.config)
        rows = db.execute(
            """SELECT t.text_hash, t.rep_id, t.rep_text, COALESCE(a.n,0) AS attempts FROM texts t
               LEFT JOIN attempts a ON a.text_hash=t.text_hash AND a.label_config=?
               WHERE NOT EXISTS (SELECT 1 FROM results r WHERE r.text_hash=t.text_hash AND r.label_config IN (?,?))
                 AND NOT EXISTS (SELECT 1 FROM quarantine q WHERE q.text_hash=t.text_hash AND q.label_config=?)
               ORDER BY t.queue_key""", (self.config, *cfgs, self.config)).fetchall()
        return [dict(r) for r in rows]

    def completed_ids(self) -> list[str]:
        """All source review IDs whose text has a result (originals + exact-text reuses)."""
        cfgs = (self.config, self.fb_config if self.fb else self.config)
        return [r[0] for r in self.store.db.execute(
            "SELECT s.review_id FROM source s WHERE s.is_empty=0 AND EXISTS (SELECT 1 FROM results r "
            "WHERE r.text_hash=s.text_hash AND r.label_config IN (?,?)) ORDER BY s.row_idx", cfgs)]

    # ------------------------------------------------------------------ worker
    def _call(self, prov, batch, max_tokens, attempt_no):
        """Runs in a worker thread. Returns attempt logs + parsed payload. No DB writes here."""
        user = build_user(batch)
        est_in = (len(self.system) + len(user)) // 3
        logs, parsed, err = [], None, None
        for t in range(DEFAULTS["transport_retries"] + 1):
            if self.stop.is_set() and t > 0:
                err = "stopped_before_retry"
                break
            self.limiter.acquire(est_in + 80 * len(batch))  # expected, not worst-case, tokens
            t0 = time.time()
            rid = "req-" + uuid.uuid4().hex[:16]
            log = {"request_id": rid, "started_at": t0, "attempt": attempt_no, "transport_try": t + 1,
                   "review_ids": [b["rep_id"] for b in batch], "provider": prov.name, "model": prov.model}
            try:
                res = prov.complete(self.system, user, self.schema, max_tokens)
            except providers.TransportError as e:
                log.update(outcome="failed", error=str(e)[:300], ended_at=time.time(), usage={},
                           usage_known=not e.usage_unknown, status=e.status)
                logs.append(log)
                if e.status in (400, 401, 403, 404, 422) or not e.retryable:
                    err = f"fatal:{e}"
                    break
                time.sleep(min(60, (2 ** t) + random.random()))  # backoff + jitter
                continue
            log.update(ended_at=time.time(), usage=res.usage, usage_known=True, provider_request_id=res.provider_request_id)
            if res.stop_reason in ("refusal", "max_tokens"):
                log.update(outcome="failed", error=f"stop_reason:{res.stop_reason}")
                logs.append(log)
                err = f"invalid_output:{res.stop_reason}"
                break
            try:
                obj = json.loads(res.text)
                if not isinstance(obj, dict) or not isinstance(obj.get("results"), list):
                    raise ValueError("no results array")
                parsed = obj["results"]
                log.update(outcome="succeeded")
            except ValueError as e:
                log.update(outcome="failed", error=f"invalid_json:{e}"[:200])
                err = "invalid_output:json"
            logs.append(log)
            break
        else:
            err = err or "transport_retries_exhausted"
        return {"batch": batch, "logs": logs, "parsed": parsed, "error": err, "attempt": attempt_no}

    # ------------------------------------------------------------------ commit
    def _commit(self, out, phase, config, prov, counters):
        db = self.store.db
        batch = {b["rep_id"]: b for b in out["batch"]}
        key_to_id = {batch_key(i): b["rep_id"] for i, b in enumerate(out["batch"])}
        self.store.begin()
        try:
            for lg in out["logs"]:
                c, _ = cost(prov.name, prov.model, lg.get("usage", {}), self.rates)
                if not lg.get("usage_known", True):
                    c = None
                u = lg.get("usage", {})
                self.store.log_call({
                    "request_id": lg["request_id"], "role": "enrich", "review_ids": lg["review_ids"], "model": prov.model,
                    "provider": prov.name, "label_config": config, "phase": phase, "outcome": lg["outcome"],
                    "error": lg.get("error"), "input_tokens": u.get("input", 0), "cached_input_tokens": u.get("cached_input", 0),
                    "cache_write_tokens": u.get("cache_write", 0), "output_tokens": u.get("output", 0),
                    "usage_known": int(bool(lg.get("usage_known", True))), "cost_usd": c, "started_at": lg["started_at"],
                    "ended_at": lg["ended_at"], "duration_s": round(lg["ended_at"] - lg["started_at"], 3),
                    "attempt": lg["attempt"], "session_id": self.session, "settings": prov.settings(),
                    "provider_request_id": lg.get("provider_request_id")})
                counters["calls"] += 1
                counters["failed_calls"] += lg["outcome"] == "failed"
                counters["spent"] += c or 0.0
            ok_ids, failed = set(), {}
            succeeded = [lg for lg in out["logs"] if lg["outcome"] == "succeeded"]
            if out["parsed"] is not None and succeeded:
                req = succeeded[-1]["request_id"]
                for it in out["parsed"]:
                    rid = key_to_id.get(it.get("k")) if isinstance(it, dict) else None
                    if rid not in batch:
                        counters["foreign_ids"] += 1        # never accept an ID we did not send
                        continue
                    if rid in ok_ids:
                        counters["duplicate_ids"] += 1
                        continue
                    rec, e = validate_item(it, batch[rid]["rep_text"])
                    if e:
                        failed[rid] = e
                        continue
                    ok_ids.add(rid)
                    failed.pop(rid, None)
                    b = batch[rid]
                    db.execute("INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (b["text_hash"], config, rid, rec["label"], rec["topic"], rec["intent"], rec["severity"],
                                rec["sentiment"], rec["evidence_quote"], rec["quote_source"], int(rec["needs_review"]),
                                rec["review_reason"], json.dumps(rec["entities"]), req, phase, self.session, time.time()))
                    counters["completed_texts"] += 1
                    counters["rows_covered"] += b.get("n", 1)
                for rid in batch:
                    if rid not in ok_ids and rid not in failed:
                        failed[rid] = "missing_id_in_response"
            else:
                for rid in batch:
                    failed[rid] = out["error"] or "call_failed"
            transport_only = out["parsed"] is None and (out["error"] or "").startswith(("transport", "fatal", "stopped"))
            for rid, e in failed.items():
                b = batch[rid]
                if transport_only:
                    counters["deferred"] += 1   # provider/transport problem: stays pending for a later session
                    continue
                db.execute("INSERT INTO attempts VALUES(?,?,1,?) ON CONFLICT(text_hash,label_config) "
                           "DO UPDATE SET n=n+1, last_error=excluded.last_error", (b["text_hash"], self.config, e))
                counters["invalid_items"] += 1
            self.store.commit()
        except BaseException:
            self.store.db.execute("ROLLBACK")
            raise
        return failed, transport_only

    def _quarantine(self, th, reason, attempts, detail):
        self.store.db.execute("INSERT OR REPLACE INTO quarantine VALUES(?,?,?,?,?)", (th, self.config, reason, attempts, detail))

    # ------------------------------------------------------------------ main loop
    def run(self) -> dict:
        db = self.store.db
        n_distinct = db.execute("SELECT COUNT(*) FROM texts").fetchone()[0]
        if n_distinct == 0:
            raise SystemExit("Nothing ingested for this run. Run `ingest` first.")
        has_prior = db.execute("SELECT COUNT(*) FROM results WHERE label_config=?", (self.config,)).fetchone()[0] > 0
        phase = "resume" if has_prior else "initial"
        if phase == "resume" and not self.store.get_meta("checkpoint_before:" + self.config):
            snap = self.completed_ids()
            self.store.set_meta("checkpoint_before:" + self.config,
                                {"saved_at": time.time(), "session": self.session, "completed_ids": snap})
            print(f"[enrich] RESUME detected: saved checkpoint_before with {len(snap):,} completed IDs")
        args = {k: getattr(self, k) for k in ("provider", "model", "effort", "workers", "budget", "batch_size",
                                              "stop_after_batches", "limit_texts")}
        args["label_config"] = self.config
        self.store.start_session(self.session, "enrich", phase, args)
        spent0 = self.store.spent()
        queue = self.pending()
        if self.limit_texts:
            queue = queue[: self.limit_texts]
        n_rows = {r[0]: r[1] for r in db.execute("SELECT text_hash, n FROM texts")}
        for q in queue:
            q["n"] = n_rows[q["text_hash"]]
        first = [q for q in queue if q["attempts"] == 0]
        retry = deque(q for q in queue if q["attempts"] >= 1)
        fresh = deque(first)
        print(f"[enrich] session {self.session} phase={phase} config={self.config}")
        print(f"[enrich] distinct texts={n_distinct:,} pending={len(queue):,} (retry {len(retry):,}) "
              f"workers={self.workers} batch<={self.batch_size} budget=${self.budget:.2f} already spent=${spent0:.4f}")
        counters = dict(calls=0, failed_calls=0, spent=0.0, completed_texts=0, rows_covered=0, invalid_items=0,
                        foreign_ids=0, duplicate_ids=0, deferred=0, quarantined=0, fallback_calls=0, batches=0)
        fb_used = db.execute("SELECT COUNT(*) FROM calls WHERE role='enrich' AND label_config=?",
                             (getattr(self, "fb_config", "-"),)).fetchone()[0]
        fb_cap = int(self.fallback_max_fraction * n_distinct) if self.fb else 0
        stop_reason = "queue_empty"
        t_start = time.time()
        reserved = {}
        consecutive_transport = 0
        old = signal.getsignal(signal.SIGINT)

        def on_sigint(sig, frm):
            if self.stop.is_set():
                raise KeyboardInterrupt
            print("\n[enrich] Ctrl-C: stopping admission, draining in-flight batches (Ctrl-C again to abort)...")
            self.stop.set()
        signal.signal(signal.SIGINT, on_sigint)

        def next_batch():
            src = retry if retry else fresh
            cap = max(1, self.batch_size // 5) if src is retry else self.batch_size  # retries go in small batches
            out, chars = [], 0
            while src and len(out) < cap:
                nxt = src[0]
                if out and chars + len(nxt["rep_text"]) > DEFAULTS["batch_char_cap"]:
                    break
                out.append(src.popleft())
                chars += len(nxt["rep_text"])
            return out

        def handle_failures(failed, transport_only):
            nonlocal fb_used
            if transport_only:
                return
            for rid, e in failed.items():
                b = by_id[rid]
                n = db.execute("SELECT n FROM attempts WHERE text_hash=? AND label_config=?",
                               (b["text_hash"], self.config)).fetchone()[0]
                if rid in fb_sent:
                    reason = "invalid_model_output_after_retry_and_fallback"
                elif n <= DEFAULTS["invalid_output_retries"]:
                    retry.append(b)                             # retry invalid output once
                    continue
                elif self.fb and fb_used < fb_cap:
                    fallback_q.append(b)                        # capped stronger-model fallback
                    fb_sent.add(rid)
                    fb_used += 1
                    continue
                else:
                    reason = "invalid_model_output_after_retry" + ("" if self.fb else " (no fallback configured)") \
                        + (" (fallback cap reached)" if self.fb and fb_used >= fb_cap else "")
                if True:
                    self.store.begin()
                    self._quarantine(b["text_hash"], reason, n, e)
                    self.store.commit()
                    counters["quarantined"] += 1

        by_id = {q["rep_id"]: q for q in queue}
        fallback_q = deque()
        fb_sent = set()
        in_flight = {}
        try:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                while True:
                    # ---- admission control
                    while not self.stop.is_set() and len(in_flight) < self.workers and (retry or fresh or fallback_q):
                        if self.max_seconds and time.time() - t_start > self.max_seconds:
                            stop_reason = "time_cap"; self.stop.set(); break
                        if self.stop_after_batches is not None and counters["batches"] >= self.stop_after_batches:
                            stop_reason = "stop_after_batches (simulated interruption)"; self.stop.set(); break
                        if fallback_q:
                            batch, prov, cfg, attempt = [fallback_q.popleft()], self.fb, self.fb_config, 3
                        else:
                            batch = next_batch()
                            prov, cfg = self.p, self.config
                            attempt = 1 + max(b["attempts"] for b in batch)
                        max_tokens = 200 + DEFAULTS["max_output_tokens_per_review"] * len(batch) + \
                            sum(len(b["rep_text"]) // 12 for b in batch) + (1500 if prov is self.fb else 0)
                        est_in = (len(self.system) + sum(len(b["rep_text"]) + 60 for b in batch)) // 3
                        res = worst_case(prov.name, prov.model, est_in, max_tokens, self.rates)
                        spent = spent0 + counters["spent"]
                        if spent + sum(reserved.values()) + res > self.budget:
                            stop_reason = f"budget_cap (spent ${spent:.4f} + reserved ${sum(reserved.values()):.4f} + next ${res:.4f} > ${self.budget:.2f})"
                            # put the batch back and stop admitting work
                            (fallback_q if prov is self.fb else (retry if attempt > 1 else fresh)).extendleft(reversed(batch))
                            self.stop.set(); break
                        fut = pool.submit(self._call, prov, batch, max_tokens, attempt)
                        in_flight[fut] = (prov, cfg)
                        reserved[fut] = res
                        counters["batches"] += 1
                        if prov is self.fb:
                            counters["fallback_calls"] += 1
                    if not in_flight:
                        break
                    done, _ = wait(list(in_flight), timeout=1.0, return_when=FIRST_COMPLETED)
                    for fut in done:
                        prov, cfg = in_flight.pop(fut)
                        reserved.pop(fut, None)
                        out = fut.result()
                        failed, transport_only = self._commit(out, phase, cfg, prov, counters)
                        if out["error"] and out["error"].startswith("fatal"):
                            print(f"[enrich] FATAL provider error, stopping: {out['error'][:200]}")
                            stop_reason = "fatal_provider_error"; self.stop.set()
                        consecutive_transport = consecutive_transport + 1 if transport_only else 0
                        if consecutive_transport >= 5 and not self.stop.is_set():
                            print("[enrich] 5 consecutive batches failed at transport level; stopping to save money/time.")
                            stop_reason = "repeated_transport_failures"; self.stop.set()
                        handle_failures(failed, transport_only)
                        if not self.quiet and counters["batches"] % 20 == 0:
                            el = time.time() - t_start
                            rate = counters["completed_texts"] / el if el else 0
                            left = len(fresh) + len(retry)
                            print(f"[enrich] {counters['completed_texts']:,} texts ({counters['rows_covered']:,} rows) | "
                                  f"${spent0 + counters['spent']:.4f} | {rate:.1f} texts/s | left {left:,} | "
                                  f"ETA {left / rate / 60 if rate else 0:.1f} min")
                    if self.stop.is_set() and stop_reason == "queue_empty":
                        stop_reason = "interrupted_by_user"
        except KeyboardInterrupt:
            stop_reason = "aborted_in_flight"
            self.store.begin()
            for fut, (prov, cfg) in in_flight.items():
                self.store.log_call({"request_id": "aborted-" + uuid.uuid4().hex[:12], "role": "enrich",
                                     "review_ids": [], "model": prov.model, "provider": prov.name, "label_config": cfg,
                                     "phase": phase, "outcome": "failed", "error": "aborted_in_flight_usage_unknown",
                                     "input_tokens": 0, "cached_input_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0,
                                     "usage_known": 0, "cost_usd": None, "session_id": self.session, "settings": prov.settings()})
            self.store.commit()
        finally:
            signal.signal(signal.SIGINT, old)
        wall = time.time() - t_start
        left = len(self.pending())
        summary = {"session": self.session, "phase": phase, "label_config": self.config, "stop_reason": stop_reason,
                   "wall_seconds": round(wall, 2), **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in counters.items()},
                   "spent_total_run_usd": round(spent0 + counters["spent"], 6), "pending_texts_after": left,
                   "throughput_texts_per_s": round(counters["completed_texts"] / wall, 3) if wall else None}
        self.store.end_session(self.session, summary)
        with (self.run_dir / "run_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "enrich_session", **summary}) + "\n")
        print(f"[enrich] done: {stop_reason} | +{counters['completed_texts']:,} texts in {wall:.1f}s | calls {counters['calls']} "
              f"(failed {counters['failed_calls']}) | session ${counters['spent']:.4f} | pending {left:,}")
        return summary
