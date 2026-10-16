#!/usr/bin/env python3
"""System checks with actual outcomes.

FREE / offline (no API key):
    python evals/system_tests.py offline --run runs/full
      1. malformed-output validation (wrong label, bad severity, foreign/missing IDs, unsupported quote)
      2. temporary API failures: mock provider with 30% transient errors -> bounded retries + backoff
      3. spend control: a $0.01 budget stops admission before overspending (test-priced mock)
      4. interruption + resume with zero re-enrichment of completed IDs (mock)
      5. planted-error test: deliberately wrong labels in a TEST COPY of the verified sample -> verifier catches them
PAID (small, explicit):
    python evals/system_tests.py injection --confirm-paid [--provider anthropic|openai]
      synthetic injected / non-English / ambiguous / empty reviews mixed into a batch of 20 real dev reviews,
      in a separate run (runs/evals-injection) that is never part of business aggregates.
Results -> evals/system_tests_report.json (+ .md)
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.config import load_dotenv, label_config  # noqa: E402
from pipeline.enrich import Enricher, validate_item  # noqa: E402
from pipeline.ingest import ingest  # noqa: E402
from pipeline.records import read_jsonl  # noqa: E402
from pipeline.store import Store  # noqa: E402
from pipeline.verify import compare, in_sample  # noqa: E402

OUT = ROOT / "evals"
TMP = ROOT / "runs" / "_systemtests"


def t_malformed():
    text = "The app crashes every time I open it"
    cases = {
        "valid": {"id": "a", "label": "playback.crash_or_wont_open", "intent": "complaint", "sev": 4, "sent": -1, "quote": "crashes every time", "flag": False},
        "unknown_label": {"id": "a", "label": "playback.explodes", "intent": "complaint", "sev": 4, "sent": -1, "quote": "crashes", "flag": False},
        "severity_out_of_range": {"id": "a", "label": "playback.crash_or_wont_open", "intent": "complaint", "sev": 7, "sent": -1, "quote": "crashes", "flag": False},
        "sentiment_out_of_range": {"id": "a", "label": "playback.crash_or_wont_open", "intent": "complaint", "sev": 4, "sent": -3, "quote": "crashes", "flag": False},
        "missing_keys": {"id": "a", "label": "playback.crash_or_wont_open"},
        "quote_paraphrased_short_text": {"id": "a", "label": "playback.crash_or_wont_open", "intent": "complaint", "sev": 4, "sent": -1, "quote": "app keeps crashing", "flag": False},
        "quote_case_whitespace": {"id": "a", "label": "playback.crash_or_wont_open", "intent": "complaint", "sev": 4, "sent": -1, "quote": "CRASHES  every time", "flag": False},
    }
    out = {}
    for name, it in cases.items():
        rec, err = validate_item(it, text)
        out[name] = {"accepted": rec is not None, "error": err,
                     "quote": rec and rec["evidence_quote"], "quote_source": rec and rec["quote_source"], "needs_review": rec and rec["needs_review"]}
    long_text = "word " * 120 + "end"
    rec, err = validate_item({**cases["valid"], "quote": "not in the text at all"}, long_text)
    out["unsupported_quote_long_text"] = {"accepted": rec is not None, "error": err}
    return out


def _fresh(name, csv_path):
    rd = TMP / name
    shutil.rmtree(rd, ignore_errors=True)
    ingest(Path(csv_path), rd)
    return rd


def t_transient():
    rd = _fresh("transient", ROOT / "data" / "checkpoint_500.csv")
    s = Enricher(rd, "mock", "mock-keywords", "none", workers=2, budget=1.0, batch_size=50, mock_fail_rate=0.3, quiet=True).run()
    db = Store(rd / "state.sqlite").db
    fails = [dict(r) for r in db.execute("SELECT error, COUNT(*) n FROM calls WHERE outcome='failed' GROUP BY 1")]
    q = db.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    return {"completed_texts": s["completed_texts"], "calls": s["calls"], "failed_calls": s["failed_calls"],
            "failed_by_error": fails, "quarantined": q, "pending_after": s["pending_texts_after"]}


def t_budget():
    rd = _fresh("budget", ROOT / "data" / "checkpoint_500.csv")
    rates = TMP / "rates_test.csv"
    rows = [l for l in (ROOT / "cost" / "rates.csv").read_text().splitlines()]
    rows = [l.replace("mock,mock-keywords,input,per_1M_tokens,0,", "mock,mock-keywords,input,per_1M_tokens,0.10,")
             .replace("mock,mock-keywords,output,per_1M_tokens,0,", "mock,mock-keywords,output,per_1M_tokens,0.50,") for l in rows]
    rates.write_text("\n".join(rows) + "\n")
    s = Enricher(rd, "mock", "mock-keywords", "none", workers=2, budget=0.01, batch_size=50, rates_path=rates, quiet=True).run()
    spent = Store(rd / "state.sqlite").spent()
    return {"budget_usd": 0.01, "spent_usd": round(spent, 6), "stop_reason": s["stop_reason"],
            "completed_texts": s["completed_texts"], "pending_after": s["pending_texts_after"], "never_exceeded": spent <= 0.01}


def t_resume():
    rd = _fresh("resume", ROOT / "data" / "checkpoint_500.csv")
    a = Enricher(rd, "mock", "mock-keywords", "none", workers=1, budget=1.0, batch_size=50, stop_after_batches=3, quiet=True).run()
    st = Store(rd / "state.sqlite")
    cfg = label_config("mock", "mock-keywords", "none")
    b = Enricher(rd, "mock", "mock-keywords", "none", workers=1, budget=1.0, batch_size=50, quiet=True).run()
    before = set(st.get_meta("checkpoint_before:" + cfg)["completed_ids"])
    resent = set()
    for r in st.db.execute("SELECT review_ids FROM calls WHERE phase='resume' AND role='enrich'"):
        resent |= set(json.loads(r[0])) & before
    after = Enricher(rd, "mock", "mock-keywords", "none", 1, 1.0, 50, quiet=True).completed_ids()
    return {"first_session": {"stop_reason": a["stop_reason"], "completed_texts": a["completed_texts"]},
            "checkpoint_before_ids": len(before), "resume_session_completed_texts": b["completed_texts"],
            "checkpoint_after_ids": len(after), "completed_ids_resent_after_resume": len(resent),
            "before_is_strict_subset_of_after": before < set(after)}


def t_planted(run: Path, n=20, seed=7):
    db = Store(run / "state.sqlite").db
    rows = [dict(r) for r in db.execute("SELECT r.text_hash, r.origin_id, r.topic, r.intent, r.severity, t.rep_text FROM results r "
                                        "JOIN texts t ON t.text_hash=r.text_hash JOIN verify v ON v.review_id=r.origin_id")]
    if not rows:
        return {"skipped": f"no verified records in {run.name}; run verify first"}
    agree = [r for r in rows if db.execute("SELECT topic FROM verify WHERE review_id=?", (r["origin_id"],)).fetchone()[0] == r["topic"]]
    rng = random.Random(seed)
    pick = rng.sample(agree, min(n, len(agree)))
    topics = ["access", "usability", "playback", "downloads", "catalog", "billing", "support", "other"]
    planted = {p["origin_id"]: {"topic": rng.choice([t for t in topics if t != p["topic"]])} for p in pick}
    rep = compare(run, None, rows, None, planted=planted)
    dis = list(csv.DictReader(open(run / "planted_error_disagreements.csv", encoding="utf-8")))
    caught = {d["review_id"] for d in dis if d["planted"] == "True" and "topic" in d["fields_disagree"]}
    shutil.copy(run / "planted_error_disagreements.csv", OUT / "planted_error_disagreements.csv")
    return {"test_copy_only": True, "planted_wrong_topics": len(planted), "caught_by_code_comparison": len(caught),
            "detection_rate": round(len(caught) / len(planted), 3) if planted else None,
            "note": "Planted only into records the verifier had independently agreed with, so every planted error should surface as a "
                    "topic disagreement. Production records are untouched (labels swapped in memory for this test copy)."}


def t_injection(provider, model, effort):
    load_dotenv()
    syn = list(csv.DictReader(open(OUT / "synthetic_cases.csv", encoding="utf-8")))
    dev = list(csv.DictReader(open(ROOT / "data" / "checkpoint_500.csv", encoding="utf-8")))[100:120]
    fields = ["review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp"]
    TMP.mkdir(parents=True, exist_ok=True)
    mixed = TMP / "injection_input.csv"
    with mixed.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        rows = [{k: r[k] for k in fields} for r in dev[:10] + syn + dev[10:]]
        w.writerows(rows)
    rd = ROOT / "runs" / "evals-injection"
    shutil.rmtree(rd, ignore_errors=True)
    ingest(mixed, rd)
    Enricher(rd, provider, model, effort, workers=1, budget=0.25, batch_size=50, fallback_provider=None).run()
    from pipeline.group import materialize
    recs = materialize(rd, (provider, model, effort))
    res = []
    for s in syn:
        r = recs[s["review_id"]]
        if not s["expected_topic"]:
            res.append({"id": s["review_id"], "purpose": s["purpose"], "status": r["status"], "reason": r.get("reason"),
                        "pass": r["status"] == "quarantined" and r.get("reason") == "empty_review_text"})
            continue
        ok_t = r.get("topic") == s["expected_topic"]
        ok_i = r.get("intent") in s["expected_intent"].split("|")
        ok_s = r.get("severity") is not None and int(s["expected_severity_min"]) <= r["severity"] <= int(s["expected_severity_max"])
        ok_f = (s["expect_flag"] != "true") or bool(r.get("needs_review"))
        res.append({"id": s["review_id"], "purpose": s["purpose"], "status": r["status"], "topic": r.get("topic"), "intent": r.get("intent"),
                    "severity": r.get("severity"), "needs_review": r.get("needs_review"), "quote": r.get("evidence_quote"),
                    "topic_ok": ok_t, "intent_ok": ok_i, "severity_ok": ok_s, "flag_ok": ok_f, "pass": ok_t and ok_i and ok_s and ok_f})
    devs = [recs[d["review_id"]] for d in dev]
    billing_share = sum(r.get("topic") == "billing" for r in devs) / len(devs)
    return {"run": rd.name, "synthetic": res, "dev_rows_in_same_batch": len(devs),
            "dev_rows_labeled_billing_share": round(billing_share, 3),
            "batch_contamination_suspected": billing_share > 0.6,
            "all_ids_accounted": all(d["review_id"] in recs for d in dev) and all(s["review_id"] in recs for s in syn),
            "note": "Synthetic cases live only in runs/evals-injection and are excluded from all business aggregates."}


def write(report):
    path = OUT / "system_tests_report.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    old.update(report)
    path.write_text(json.dumps(old, indent=2, ensure_ascii=False, default=str) + "\n")
    md = ["# System tests: actual outcomes", "", f"Updated {time.strftime('%Y-%m-%d %H:%M')}. Raw: `system_tests_report.json`.", ""]
    for k, v in old.items():
        md += [f"## {k}", "", "```json", json.dumps(v, indent=2, ensure_ascii=False, default=str), "```", ""]
    (OUT / "system_tests_report.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)[:4000])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("offline"); p.add_argument("--run", default=None, help="verified run for the planted-error test")
    p = sub.add_parser("injection"); p.add_argument("--confirm-paid", action="store_true")
    p.add_argument("--provider", default="anthropic"); p.add_argument("--model", default=None); p.add_argument("--effort", default=None)
    a = ap.parse_args()
    if a.cmd == "offline":
        rep = {"malformed_output_validation": t_malformed(), "transient_api_failures_mock": t_transient(),
               "spend_cap_mock": t_budget(), "interrupt_resume_mock": t_resume()}
        if a.run:
            rep["planted_error_test"] = t_planted(Path(a.run) if Path(a.run).is_absolute() else ROOT / a.run)
        write(rep)
    else:
        if not a.confirm_paid:
            raise SystemExit("Paid test: add --confirm-paid")
        model = a.model or {"anthropic": "claude-haiku-5-5", "openai": "gpt-6-luna", "mock": "mock-keywords"}[a.provider]
        effort = a.effort or {"anthropic": "low", "openai": "none", "mock": "none"}[a.provider]
        write({"injection_and_hard_cases": t_injection(a.provider, model, effort)})


if __name__ == "__main__":
    main()
