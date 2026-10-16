#!/usr/bin/env python3
"""100-review cost & runtime calculator (COST_CALCULATOR.md).

OFFLINE REPLAY (default, no API key, no model calls):
    python cost/calculator.py
    python cost/calculator.py --rate-multiplier 2          # doubles API spend, time unchanged
    python cost/calculator.py --rates cost/rates.csv --assumptions cost/assumptions.json

EXPLICIT PAID PILOT (real calls on data/cost_100.csv, empty cache, 1 worker, cold then warm):
    python cost/calculator.py pilot --confirm-paid

REFRESH ESTIMATE FROM A LARGER CHECKPOINT RUN (no calls; reads that run's saved call log):
    python cost/calculator.py refresh --run runs/ckpt500 --label checkpoint_500
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from pipeline.rates import ITEMS, load_rates, per_unit  # noqa: E402

COST_100_SHA = "c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e"
FULL = {"rows": 660_622, "nonempty": 660_609, "empty": 13, "distinct": 484_189}


# --------------------------------------------------------------------------- arithmetic
def call_cost(call, rates):
    """Itemised cost of one logged call: billed_units x price_per_unit, mutually exclusive items."""
    usage = {"input": call.get("uncached_input_tokens", 0), "cached_input": call.get("cached_input_tokens", 0),
             "cache_write": call.get("cache_write_tokens", 0), "output": call.get("output_tokens", 0)}
    lines, total, unknown = [], 0.0, False
    for item in ITEMS:
        units = int(usage[item] or 0)
        if not units:
            continue
        r = rates.get((call["provider"], call["model_rate_key"], item))
        pu = per_unit(r)
        c = None if pu is None else units * pu
        unknown |= c is None
        total += c or 0.0
        lines.append({"request_id": call["request_id"], "run_phase": call["run_phase"], "role": call["role"],
                      "provider": call["provider"], "model": call["model_rate_key"], "item": item, "units": units,
                      "unit": (r or {}).get("unit", "per_1M_tokens"), "price": None if r is None else r["price"],
                      "price_per_unit": pu, "cost_usd": c, "rate_status": (r or {}).get("status", "missing"),
                      "rate_source": (r or {}).get("source", ""), "rate_checked": (r or {}).get("checked", "")})
    if not call.get("usage_known", True):
        unknown = True
    return (None if unknown else total), lines, unknown


def load_calls(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def stage_table(calls, rates, run_phase):
    out = {}
    for c in calls:
        if c["run_phase"] != run_phase:
            continue
        s = out.setdefault(c["role"], {"provider": c["provider"], "model": c["model"], "settings": c.get("settings"),
                                       "label_config": c.get("label_config"), "requests": 0, "failed": 0, "review_ids_sent": 0,
                                       "uncached_input": 0, "cached_input": 0, "cache_write": 0, "output": 0,
                                       "cost_usd": 0.0, "unknown_cost_calls": 0})
        cost, _, unknown = call_cost(c, rates)
        s["requests"] += 1
        s["failed"] += c["outcome"] == "failed"
        s["review_ids_sent"] += len(c.get("review_ids", []))
        s["uncached_input"] += c.get("uncached_input_tokens", 0)
        s["cached_input"] += c.get("cached_input_tokens", 0)
        s["cache_write"] += c.get("cache_write_tokens", 0)
        s["output"] += c.get("output_tokens", 0)
        s["cost_usd"] += cost or 0.0
        s["unknown_cost_calls"] += unknown
    return out


# --------------------------------------------------------------------------- projection
def fallback_unit_cost(a, rates):
    t = a["fallback_tokens_per_review"]
    total = 0.0
    for item in ITEMS:
        units = t.get(item, 0)
        if units:
            pu = per_unit(rates.get((a["fallback_provider"], a["fallback_model"], item)))
            total += units * (pu or 0.0)
    return total


def project(measured, assumptions, rates):
    a = assumptions
    enr = measured["cold"]["stages"].get("enrich", {})
    texts = max(1, measured["cold"]["distinct_texts_enriched"])
    per_text = enr.get("cost_usd", 0.0) / texts
    out_per_text = enr.get("output", 0) / texts
    fail_rate = enr.get("failed", 0) / max(1, enr.get("requests", 1))
    ver = measured["cold"]["stages"].get("verify", {})
    ver_per = (ver.get("cost_usd", 0.0) / max(1, ver.get("review_ids_sent", 1))) if ver else 0.0
    ver_unknown = bool(ver.get("unknown_cost_calls")) if ver else False
    fixed = sum(measured["cold"]["stages"].get(r, {}).get("cost_usd", 0.0) for r in ("group", "memo"))
    wall_enrich = measured["cold"]["stage_wall_seconds"].get("enrich", 0.0)
    tput1 = texts / wall_enrich if wall_enrich else None   # texts/s at the measured worker count
    fb_cost_each = fallback_unit_cost(a, rates)
    scen = {}
    for name, k in (("base", a["base"]), ("conservative", a["conservative"])):
        rows = {}
        for label, n_texts in (("with_exact_text_reuse", a["projected_distinct_texts"]),
                               ("no_reuse", a["projected_nonempty_rows"])):
            retry_mult = 1 + max(fail_rate, k["retry_rate"])
            enrich = per_text * n_texts * retry_mult * k["output_multiplier_on_cost"]
            n_ver = min(a["verify_max"], round(a["verify_rate"] * n_texts))
            verify = ver_per * n_ver
            n_fb = round(k["fallback_fraction"] * n_texts)
            fallback = fb_cost_each * n_fb
            total = enrich + verify + fallback + fixed
            if a.get("enrich_mode") == "batch":
                # Message Batches: provider-scheduled. hours = rounds of in-flight jobs x job turnaround (modeled)
                per_req = max(1.0, measured["cold"]["distinct_texts_enriched"] / max(1, enr.get("requests", 1) - enr.get("failed", 0)))
                jobs = math.ceil(n_texts * retry_mult / per_req / a["batch_requests_per_job"])
                rounds = math.ceil(jobs / a["batch_max_inflight_jobs"])
                turn = max(a["batch_job_turnaround_minutes"][name], wall_enrich / 60)
                hours = rounds * turn / 60
            else:
                workers = a["max_workers"]
                hours = (n_texts * retry_mult / (tput1 * workers * a["parallel_efficiency"]) / 3600) if tput1 else None
            rows[label] = {"distinct_texts_sent": n_texts, "enrich_usd": round(enrich, 4), "verify_usd": round(verify, 4),
                           "verify_reviews": n_ver, "verify_cost_unknown": ver_unknown, "fallback_usd": round(fallback, 4),
                           "fallback_reviews": n_fb, "fixed_group_memo_usd": round(fixed, 4), "total_api_usd": round(total, 4),
                           "usd_per_100k_rows": round(total / a["projected_rows"] * 100_000, 4),
                           "enrich_hours_modeled": round(hours, 2) if hours else None,
                           "over_budget": total > a["budget_usd"]}
        scen[name] = {"assumptions": k, **rows}
    return {"fallback_usd_per_review": fb_cost_each, "per_distinct_text_enrich_usd": per_text, "output_tokens_per_text": round(out_per_text, 2),
            "measured_enrich_failure_rate": round(fail_rate, 4), "measured_throughput_texts_per_s": round(tput1, 3) if tput1 else None,
            "verify_usd_per_review": ver_per, "fixed_overhead_usd_once": fixed, "scenarios": scen}


# --------------------------------------------------------------------------- report
def replay(args):
    rates = load_rates(Path(args.rates), multiplier=args.rate_multiplier)
    assumptions = json.loads(Path(args.assumptions).read_text())
    if args.budget is not None:
        assumptions["budget_usd"] = args.budget
    if args.rows is not None:
        assumptions["projected_rows"] = args.rows
    pilot = json.loads((HERE / "pilot_measurements.json").read_text())
    calls = load_calls(HERE / "pilot_calls.jsonl")
    usage_rows = []
    for c in calls:
        usage_rows += call_cost(c, rates)[1]
    with (HERE / "usage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(usage_rows[0].keys()) if usage_rows else ["request_id"])
        w.writeheader(); w.writerows(usage_rows)
    measured = {}
    for phase in ("cold", "warm"):
        p = pilot[phase]
        st = stage_table(calls, rates, phase)
        api = sum(s["cost_usd"] for s in st.values())
        measured[phase] = {**p, "stages": st, "api_usd": round(api, 6),
                           "usd_per_1000_inputs": round(api / p["input_rows"] * 1000, 6),
                           "usd_per_completed_record": round(api / p["completed"], 8) if p["completed"] else None,
                           "unknown_cost_calls": sum(s["unknown_cost_calls"] for s in st.values())}
    proj = project(measured, assumptions, rates)
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "rate_multiplier": args.rate_multiplier,
              "rates_file": str(args.rates), "pilot": {k: pilot[k] for k in ("input", "run_ids", "settings")},
              "measured": measured, "projection": proj, "assumptions": assumptions,
              "local_compute": {"api_usd": 0, "local_hardware_cost": "unknown (laptop orchestrator; not metered)",
                                "note": "Kept separate from API spend; never folded into zero."}}
    (HERE / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (HERE / "report.md").write_text(render(report), encoding="utf-8")
    c, w = measured["cold"], measured["warm"]
    print(f"[calculator] OFFLINE replay (no API calls). rates x{args.rate_multiplier}")
    print(f"  cold: ${c['api_usd']:.6f} API, {c['wall_seconds']:.1f}s wall, {c['completed']}/{c['input_rows']} completed")
    print(f"  warm: ${w['api_usd']:.6f} API, {w['wall_seconds']:.1f}s wall, enrich calls={w['stages'].get('enrich', {}).get('requests', 0)}")
    for name, s in proj["scenarios"].items():
        r = s["with_exact_text_reuse"]
        print(f"  full run {name}: ${r['total_api_usd']:.2f} (${r['usd_per_100k_rows']:.2f}/100k rows) "
              f"no-reuse ${s['no_reuse']['total_api_usd']:.2f} | ~{r['enrich_hours_modeled']} h | "
              f"{'OVER BUDGET' if r['over_budget'] else 'within budget'} ${assumptions['budget_usd']:.2f}")
    print("  wrote cost/report.md, cost/report.json, cost/usage.csv")


def fmt(x, d=6):
    return "unknown" if x is None else f"{x:,.{d}f}"


def render(r):
    m, p, a = r["measured"], r["projection"], r["assumptions"]
    pil = r["pilot"]
    L = ["# 100-review cost & runtime calculator report", "",
         f"Generated {r['generated_at']} by `python cost/calculator.py` (offline replay of saved usage; rate multiplier {r['rate_multiplier']}).",
         "Every API dollar below = billed units x price per unit from `cost/rates.csv`; itemised per call in `cost/usage.csv`.", "",
         "## Measured: real 100-review pilot", "",
         f"- Input: `{pil['input']['name']}` sha256 `{pil['input']['sha256']}` (expected `{COST_100_SHA}`: "
         f"{'MATCH' if pil['input']['sha256'] == COST_100_SHA else 'MISMATCH'}), {pil['input']['rows']} IDs",
         f"- Run IDs: cold `{pil['run_ids']['cold']}`, warm `{pil['run_ids']['warm']}` (same run state, unchanged settings)",
         f"- Settings: `{json.dumps(pil['settings'])}`", "",
         "| | cold (empty result cache) | warm (saved results) |", "|---|---|---|"]
    for key, label in (("input_rows", "input rows"), ("completed", "completed"), ("quarantined", "quarantined / failed"),
                       ("unique_texts", "unique texts"), ("distinct_texts_enriched", "texts sent to enrichment"),
                       ("result_cache_hits", "result-cache hits (texts)"), ("wall_seconds", "end-to-end wall-clock s")):
        L.append(f"| {label} | {m['cold'].get(key)} | {m['warm'].get(key)} |")
    L.append(f"| API spend (USD) | {fmt(m['cold']['api_usd'])} | {fmt(m['warm']['api_usd'])} |")
    L.append(f"| USD per 1,000 inputs | {fmt(m['cold']['usd_per_1000_inputs'])} | {fmt(m['warm']['usd_per_1000_inputs'])} |")
    L.append(f"| USD per completed record | {fmt(m['cold']['usd_per_completed_record'], 8)} | {fmt(m['warm']['usd_per_completed_record'], 8)} |")
    L.append(f"| throughput (rows/s, end to end) | {m['cold']['input_rows'] / m['cold']['wall_seconds']:.2f} | "
             f"{m['warm']['input_rows'] / max(m['warm']['wall_seconds'], 1e-9):.2f} |")
    L.append(f"| calls with unknown cost | {m['cold']['unknown_cost_calls']} | {m['warm']['unknown_cost_calls']} |")
    for phase in ("cold", "warm"):
        L += ["", f"### Stages ({phase})", "",
              "| stage | provider / model | label config | requests | failed | review IDs sent | uncached in | cached in | cache write | output | API USD | wall s |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for role in ("enrich", "verify", "group", "memo"):
            s = m[phase]["stages"].get(role)
            ws = m[phase]["stage_wall_seconds"].get(role, 0)
            if not s:
                L.append(f"| {role} | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | {ws} |")
                continue
            L.append(f"| {role} | {s['provider']} / `{s['model']}` | `{s['label_config']}` | {s['requests']} | {s['failed']} | "
                     f"{s['review_ids_sent']} | {s['uncached_input']:,} | {s['cached_input']:,} | {s['cache_write']:,} | {s['output']:,} | "
                     f"{fmt(s['cost_usd'])}{' + unknown' if s['unknown_cost_calls'] else ''} | {ws} |")
        L.append(f"| rank (code) | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | {m[phase]['stage_wall_seconds'].get('rank', 0)} |")
    L += ["", "Batch size: enrichment <= 50 reviews/request (char cap 14,000); workers: 1 (pilot). Summed call durations are not used as wall time.", "",
          "## Rates used (editable: `cost/rates.csv`)", "", "| provider | model | item | price | unit | status | source | checked |", "|---|---|---|---|---|---|---|---|"]
    with open(r["rates_file"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            L.append(f"| {row['provider']} | {row['model']} | {row['item']} | {row['price_usd'] or 'UNKNOWN'} | {row['unit']} | "
                     f"{row['status']} | {row['source_url']} | {row['checked_date']} |")
    L += ["", "## Full-run projection (estimates, not measurements)", "",
          f"Scope: {a['projected_rows']:,} rows -> {a['projected_nonempty_rows']:,} nonempty classifications + "
          f"{a['projected_rows'] - a['projected_nonempty_rows']} empty-text quarantines; {a['projected_distinct_texts']:,} distinct texts with exact-text reuse.",
          f"Measured basis: ${p['per_distinct_text_enrich_usd']:.8f} enrichment per distinct text; {p['output_tokens_per_text']} output tokens/text; "
          f"enrichment failure rate {p['measured_enrich_failure_rate']}; throughput {p['measured_throughput_texts_per_s']} texts/s at 1 worker; "
          f"verify ${p['verify_usd_per_review']:.8f}/review; fallback ${p['fallback_usd_per_review']:.6f}/review (rates x assumed tokens); fixed group+memo ${p['fixed_overhead_usd_once']:.6f} once (not multiplied by rows).", "",
          f"Controls: budget **${a['budget_usd']:.2f}** (course cap $10 per 100k rows), max workers {a['max_workers']}, "
          f"output cap {a['output_token_cap_per_review']} tokens/review + 200/request, fallback cap {a['fallback_max_fraction']:.2%} of distinct texts, "
          f"verify rate {a['verify_rate']:.1%} (max {a['verify_max']}).", "",
          "| scenario | reuse | texts sent | enrich $ | verify $ | fallback $ | fixed $ | total API $ | $/100k rows | enrich hours (modeled) | budget |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in p["scenarios"].items():
        for lab in ("with_exact_text_reuse", "no_reuse"):
            x = s[lab]
            L.append(f"| {name} | {lab} | {x['distinct_texts_sent']:,} | {x['enrich_usd']:.2f} | {x['verify_usd']:.2f}"
                     f"{'+unknown' if x['verify_cost_unknown'] else ''} | {x['fallback_usd']:.2f} | {x['fixed_group_memo_usd']:.4f} | "
                     f"**{x['total_api_usd']:.2f}** | {x['usd_per_100k_rows']:.2f} | {x['enrich_hours_modeled']} | "
                     f"{'**OVER BUDGET**' if x['over_budget'] else 'ok'} |")
    L += ["", "Scenario assumptions: " + "; ".join(f"{n}: {json.dumps(s['assumptions'])}" for n, s in p["scenarios"].items()),
          "", ("Hours (batch mode) are modeled as ceil(jobs / max in-flight jobs) x job turnaround, using the larger of the measured pilot "
               f"turnaround ({m['cold']['stage_wall_seconds'].get('enrich', 0) / 60:.1f} min) and the scenario assumption "
               f"({a.get('batch_job_turnaround_minutes')} min); the provider's SLA is < 24 h per job. Not measured; refresh after 500 and 10,000."
               if a.get("enrich_mode") == "batch" else
               "Hours are modeled from the 1-worker pilot throughput x workers x parallel efficiency, not measured; refresh after 500 and 10,000."),
          "", "## Local compute (separate from API spend)", "", f"- {r['local_compute']['local_hardware_cost']}. {r['local_compute']['note']}"]
    ref = HERE / "checkpoints.json"
    if ref.exists():
        L += ["", "## Refreshed estimates from larger checkpoints (measured on those runs)", "",
              "| checkpoint | rows | distinct texts | enrich calls | failed | enrich $ | $/distinct text | texts/s | workers | projected full $ (reuse) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for c in json.loads(ref.read_text()):
            L.append(f"| {c['label']} | {c['rows']:,} | {c['distinct_texts']:,} | {c['enrich_calls']} | {c['enrich_failed']} | "
                     f"{c['enrich_usd']:.4f} | {c['usd_per_text']:.8f} | {c['texts_per_s']} | {c['workers']} | {c['projected_full_usd']:.2f} |")
    L += ["", "## Reproduce", "", "```sh", "python cost/calculator.py                       # offline replay (default)",
          "python cost/calculator.py --rate-multiplier 2   # check: API $ doubles, time unchanged",
          "python cost/calculator.py --rows 100000         # change projected volume; measured pilot unchanged",
          "python cost/calculator.py pilot --confirm-paid  # explicit, paid: real cold+warm pilot", "```", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- paid pilot
def pilot(args):
    if not args.confirm_paid:
        raise SystemExit("Refusing to make paid calls without --confirm-paid.")
    from pipeline.config import load_dotenv, label_config
    from pipeline.ingest import ingest
    from pipeline.enrich import Enricher
    from pipeline.verify import verify
    from pipeline.group import group
    from pipeline.rank import rank_run
    from pipeline.memo import memo
    from pipeline.export import call_rows
    from pipeline.records import read_jsonl, grading_view
    from pipeline.sourceio import file_sha
    from pipeline.store import Store
    load_dotenv()
    src = Path(args.input)
    sha = file_sha(src)
    if sha != COST_100_SHA and not args.allow_other_input:
        raise SystemExit(f"{src} sha256 {sha} != cost_100.csv {COST_100_SHA}")
    run_id = args.run or "pilot100-" + time.strftime("%Y%m%d-%H%M%S")
    rd = ROOT / "runs" / run_id
    if rd.exists() and not args.resume_existing:
        raise SystemExit(f"{rd} exists; the cold pilot needs an empty result cache. Use a new --run.")
    cfg = (args.provider, args.model, args.effort)
    measures = {}
    for phase in ("cold", "warm"):
        times = {}
        t_all = time.time()
        t = time.time(); ingest(src, rd); times["ingest"] = round(time.time() - t, 3)
        st = Store(rd / "state.sqlite")
        pend_before = len(Enricher(rd, *cfg, 1, args.budget, 50, fallback_provider=None).pending())
        t = time.time()
        from pipeline.batch_enrich import BatchEnricher
        cls = BatchEnricher if args.mode == "batch" and args.provider in ("anthropic", "mock") else Enricher
        kw = dict(poll_seconds=15) if cls is BatchEnricher else {}
        cls(rd, *cfg, workers=1, budget=args.budget, batch_size=50, fallback_provider=args.fallback_provider or None,
            fallback_model=args.fallback_model, **kw).run()
        times["enrich"] = round(time.time() - t, 3)
        t = time.time(); verify(rd, cfg, args.verify_provider, None, args.verify_rate, 1000, 1); times["verify"] = round(time.time() - t, 3)
        t = time.time(); group(rd, cfg, args.provider); times["group"] = round(time.time() - t, 3)
        t = time.time(); rank_run(rd); times["rank"] = round(time.time() - t, 3)
        t = time.time(); memo(rd, cfg, args.provider, args.memo_model); times["memo"] = round(time.time() - t, 3)
        wall = round(time.time() - t_all, 3)
        recs = list(read_jsonl(rd / "enriched.jsonl"))
        n_texts = st.db.execute("SELECT COUNT(*) FROM texts").fetchone()[0]
        measures[phase] = {"run_id": f"{run_id}:{phase}", "input_rows": len(recs), "completed": sum(r["status"] == "completed" for r in recs),
                           "quarantined": sum(r["status"] == "quarantined" for r in recs), "unique_texts": n_texts,
                           "distinct_texts_enriched": pend_before, "result_cache_hits": n_texts - pend_before,
                           "wall_seconds": wall, "stage_wall_seconds": times, "calls_upto": st.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]}
    # split call log into cold / warm by order of insertion
    st = Store(rd / "state.sqlite")
    allc = list(call_rows(st))
    cold_n = measures["cold"]["calls_upto"]
    old = HERE / "pilot_measurements.json"
    if old.exists():   # keep earlier attempts (and their real failures) instead of overwriting them
        prev = json.loads(old.read_text())["run_ids"]["cold"].split(":")[0]
        hist = HERE / "history" / prev
        hist.mkdir(parents=True, exist_ok=True)
        for name in ("pilot_measurements.json", "pilot_calls.jsonl", "pilot_records.jsonl", "report.md", "report.json", "usage.csv"):
            if (HERE / name).exists():
                (HERE / name).replace(hist / name)
        print(f"[pilot] archived previous pilot evidence to cost/history/{prev}/")
    with (HERE / "pilot_calls.jsonl").open("w", encoding="utf-8") as f:
        for i, c in enumerate(allc):
            c["run_phase"] = "cold" if i < cold_n else "warm"
            c["run_id"] = measures[c["run_phase"]]["run_id"]
            c["model_rate_key"] = c["model"] if c["provider"] != "jev" else "jev-latest"
            c["settings"] = json.loads(st.db.execute("SELECT settings FROM calls WHERE request_id=?", (c["request_id"],)).fetchone()[0])
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (HERE / "pilot_records.jsonl").open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(grading_view(r), ensure_ascii=False) + "\n")
    pilot_meta = {"input": {"name": src.name, "sha256": sha, "rows": measures["cold"]["input_rows"]},
                  "run_ids": {"cold": measures["cold"]["run_id"], "warm": measures["warm"]["run_id"]},
                  "settings": {"enrich": label_config(*cfg), "mode": args.mode, "workers": 1, "batch_size": 50, "verify": args.verify_provider,
                               "verify_rate": args.verify_rate, "fallback": args.fallback_model if args.fallback_provider else None},
                  **measures}
    (HERE / "pilot_measurements.json").write_text(json.dumps(pilot_meta, indent=2) + "\n")
    for f in ("enriched.jsonl.gz", "memo.md", "ranking.csv", "verification_report.json", "issues.json"):
        if (rd / f).exists():
            (HERE / "pilot_outputs").mkdir(exist_ok=True)
            (HERE / "pilot_outputs" / f).write_bytes((rd / f).read_bytes())
    print(f"[pilot] saved cost/pilot_calls.jsonl ({len(allc)} calls), pilot_records.jsonl, pilot_measurements.json")
    replay(argparse.Namespace(rates=str(HERE / "rates.csv"), assumptions=str(HERE / "assumptions.json"),
                              rate_multiplier=1.0, budget=None, rows=None))


def refresh(args):
    from pipeline.store import Store
    rd = Path(args.run) if Path(args.run).is_absolute() else ROOT / args.run
    st = Store(rd / "state.sqlite")
    db = st.db
    rows = db.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    distinct = db.execute("SELECT COUNT(*) FROM texts").fetchone()[0]
    e = db.execute("SELECT COUNT(*), SUM(outcome='failed'), SUM(cost_usd) FROM calls WHERE role='enrich'").fetchone()
    sess = [json.loads(s[0]) for s in db.execute("SELECT summary FROM sessions WHERE stage='enrich' AND summary IS NOT NULL")]
    texts = sum(s.get("completed_texts", 0) for s in sess)
    wall = sum(s.get("wall_seconds", 0) for s in sess)
    workers = max((json.loads(a[0]).get("workers", 1) for a in db.execute("SELECT args FROM sessions WHERE stage='enrich'")), default=1)
    per = (e[2] or 0) / max(1, texts)
    entry = {"label": args.label, "run": rd.name, "rows": rows, "distinct_texts": distinct, "enrich_calls": e[0],
             "enrich_failed": e[1] or 0, "enrich_usd": e[2] or 0.0, "usd_per_text": per,
             "texts_per_s": round(texts / wall, 2) if wall else None, "workers": workers,
             "projected_full_usd": per * FULL["distinct"]}
    path = HERE / "checkpoints.json"
    data = [c for c in (json.loads(path.read_text()) if path.exists() else []) if c["label"] != args.label] + [entry]
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"[refresh] {args.label}: ${entry['enrich_usd']:.4f} for {texts:,} texts -> ${per:.8f}/text -> "
          f"full-run enrichment ~${entry['projected_full_usd']:.2f} (reuse). Re-run replay to update report.md.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rates", default=str(HERE / "rates.csv"))
    ap.add_argument("--assumptions", default=str(HERE / "assumptions.json"))
    ap.add_argument("--rate-multiplier", type=float, default=1.0)
    ap.add_argument("--budget", type=float, default=None)
    ap.add_argument("--rows", type=int, default=None, help="projected row count (does not change measured pilot)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("pilot", help="PAID: real cold+warm pilot on cost_100.csv")
    p.add_argument("--confirm-paid", action="store_true")
    p.add_argument("--input", default=str(ROOT / "data" / "cost_100.csv"))
    p.add_argument("--run", default=None)
    p.add_argument("--provider", default="anthropic"); p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--effort", default="low")
    p.add_argument("--verify-provider", default="jev"); p.add_argument("--verify-rate", type=float, default=0.2)
    p.add_argument("--fallback-provider", default="anthropic"); p.add_argument("--fallback-model", default="claude-haiku-5-5")
    p.add_argument("--mode", default="batch", choices=["batch", "sync"])
    p.add_argument("--memo-model", default=None)
    p.add_argument("--budget", type=float, default=1.0)
    p.add_argument("--allow-other-input", action="store_true"); p.add_argument("--resume-existing", action="store_true")
    p = sub.add_parser("refresh", help="add a 500 / 10,000 checkpoint measurement (no calls)")
    p.add_argument("--run", required=True); p.add_argument("--label", required=True)
    args = ap.parse_args()
    if args.cmd == "pilot":
        pilot(args)
    elif args.cmd == "refresh":
        refresh(args)
    else:
        replay(args)


if __name__ == "__main__":
    main()
