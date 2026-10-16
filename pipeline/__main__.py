"""Command-line orchestrator.

  python -m pipeline run      --input CSV --run ID [paid model calls]   # all six stages
  python -m pipeline ingest   --input CSV --run ID                      # code only
  python -m pipeline enrich   --run ID [--workers N --budget USD ...]   # paid (enrichment agent)
  python -m pipeline verify   --run ID                                  # paid (verifier agent)
  python -m pipeline group    --run ID                                  # paid, small (issue-naming agent)
  python -m pipeline rank     --run ID                                  # code only, no model
  python -m pipeline memo     --run ID                                  # paid, small (memo agent)
  python -m pipeline export   --run ID --out grading                    # code only
  python -m pipeline rerank   --grading grading                         # code only: ranking from saved outputs
  python -m pipeline status   --run ID                                  # code only

Use `--provider mock` for a free offline dry run (never exported as real results).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .config import DEFAULTS, ROOT, load_dotenv


def run_dir(args) -> Path:
    return (ROOT / "runs" / args.run) if not Path(args.run).is_absolute() else Path(args.run)


def budget_for(store_rows: int, args) -> float:
    if args.budget is not None:
        return args.budget
    return round(max(1.0, DEFAULTS["budget_usd_per_100k"] * store_rows / 100_000), 2)


def add_model_args(p):
    p.add_argument("--provider", default=DEFAULTS["enrich_provider"], help="anthropic | openai | mock")
    p.add_argument("--model", default=None)
    p.add_argument("--effort", default=None, help="anthropic: low (thinking disabled); openai: none")
    p.add_argument("--mode", default=DEFAULTS["mode"], choices=["batch", "sync"],
                   help="batch: Anthropic Message Batches API (50%% price, async); sync: standard API with worker threads")
    p.add_argument("--requests-per-job", type=int, default=400, help="batch mode: requests (each <= 50 reviews) per Message Batch job")
    p.add_argument("--max-inflight-jobs", type=int, default=4)
    p.add_argument("--poll-seconds", type=int, default=30)
    p.add_argument("--workers", type=int, default=DEFAULTS["workers"])
    p.add_argument("--batch-size", type=int, default=DEFAULTS["batch_size"])
    p.add_argument("--budget", type=float, default=None, help="USD cap for this run (default: $10 per 100k input rows)")
    p.add_argument("--max-minutes", type=float, default=None)
    p.add_argument("--stop-after-batches", type=int, default=None, help="simulate an interruption after N batches")
    p.add_argument("--limit-texts", type=int, default=None)
    p.add_argument("--no-fallback", action="store_true")
    p.add_argument("--fallback-provider", default=DEFAULTS["fallback_provider"])
    p.add_argument("--fallback-model", default=DEFAULTS["fallback_model"])
    p.add_argument("--fallback-effort", default=DEFAULTS["fallback_effort"])
    p.add_argument("--fallback-max-fraction", type=float, default=DEFAULTS["fallback_max_fraction"])
    p.add_argument("--rpm", type=int, default=1000, help="shared requests/min cap; set to your provider tier")
    p.add_argument("--tpm", type=int, default=2_000_000, help="shared tokens/min cap; set to your provider tier")
    p.add_argument("--mock-fail-rate", type=float, default=0.0)
    p.add_argument("--verify-provider", default=DEFAULTS["verify_provider"], help="jev | anthropic | openai | mock")
    p.add_argument("--verify-model", default=None)
    p.add_argument("--verify-rate", type=float, default=DEFAULTS["verify_rate"])
    p.add_argument("--verify-max", type=int, default=6000)
    p.add_argument("--group-provider", default=None)
    p.add_argument("--memo-provider", default=None)
    p.add_argument("--memo-model", default=None)


def resolve(args):
    prov = args.provider
    model = args.model or {"anthropic": "claude-haiku-5-5", "openai": "gpt-6-luna", "mock": "mock-keywords"}[prov]
    effort = args.effort or {"anthropic": "low", "openai": "none", "mock": "none"}[prov]
    return prov, model, effort


def cmd_enrich(args):
    from .enrich import Enricher
    from .batch_enrich import BatchEnricher
    from .store import Store
    rd = run_dir(args)
    rows = Store(rd / "state.sqlite").db.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    prov, model, effort = resolve(args)
    fbp = None if args.no_fallback or prov == "mock" else args.fallback_provider
    batch_mode = args.mode == "batch" and prov in ("anthropic", "mock")
    extra = dict(requests_per_job=args.requests_per_job, max_inflight_jobs=args.max_inflight_jobs,
                 poll_seconds=args.poll_seconds) if batch_mode else {}
    cls = BatchEnricher if batch_mode else Enricher
    if args.mode == "batch" and not batch_mode:
        print(f"[enrich] --mode batch is only implemented for anthropic; using sync for {prov}")
    e = cls(rd, prov, model, effort, args.workers, budget_for(rows, args), args.batch_size,
                 max_minutes=args.max_minutes, stop_after_batches=args.stop_after_batches, limit_texts=args.limit_texts,
                 fallback_provider=fbp, fallback_model=args.fallback_model, fallback_max_fraction=args.fallback_max_fraction,
                 fallback_effort=args.fallback_effort,
                 rpm=args.rpm, tpm=args.tpm, mock_fail_rate=args.mock_fail_rate, **extra)
    return e.run()


def cmd_verify(args):
    from .verify import verify
    prov, model, effort = resolve(args)
    vp = "mock" if prov == "mock" else args.verify_provider
    return verify(run_dir(args), (prov, model, effort), vp, args.verify_model, args.verify_rate, args.verify_max,
                  args.workers, budget=args.budget)


def cmd_group(args):
    from .group import group
    prov, model, effort = resolve(args)
    gp = "mock" if prov == "mock" else (args.group_provider or DEFAULTS["group_provider"])
    return group(run_dir(args), (prov, model, effort), gp)


def cmd_rank(args):
    from .rank import rank_run
    return rank_run(run_dir(args))


def cmd_memo(args):
    from .memo import memo
    prov, model, effort = resolve(args)
    mp = "mock" if prov == "mock" else (args.memo_provider or DEFAULTS["memo_provider"])
    return memo(run_dir(args), (prov, model, effort), mp, args.memo_model)


def cmd_export(args):
    from .export import export
    prov, model, effort = resolve(args)
    return export(run_dir(args), (prov, model, effort), Path(args.out) if args.out else None, allow_mock=args.allow_mock)


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("--input", required=True); p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true")
    for name in ("enrich", "verify", "group", "memo", "rank", "export", "run", "status"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        add_model_args(p)
        if name == "run":
            p.add_argument("--input", required=True)
            p.add_argument("--skip", default="", help="comma list of stages to skip, e.g. verify,memo")
        if name in ("export", "run"):
            p.add_argument("--out", default=None, help="grading export folder (default runs/<id>/grading)")
            p.add_argument("--allow-mock", action="store_true", help="tests only: allow exporting mock labels")
    p = sub.add_parser("smoke", help="PAID ~$0.001: check key + request shape on 3 reviews")
    p.add_argument("--provider", default=DEFAULTS["enrich_provider"]); p.add_argument("--model", default=None)
    p.add_argument("--effort", default=None); p.add_argument("--mode", default=DEFAULTS["mode"])
    p = sub.add_parser("report", help="write docs/RESULTS.md from saved outputs (no model)")
    p.add_argument("--run", required=True)
    p = sub.add_parser("rerank", help="recompute ranking.csv from saved records + membership (no model)")
    p.add_argument("--grading", required=True); p.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.cmd == "ingest":
        from .ingest import ingest
        ingest(Path(args.input), run_dir(args), force=args.force)
    elif args.cmd == "smoke":
        from .smoke import smoke
        smoke(*resolve(args), mode=args.mode)
    elif args.cmd == "report":
        from .report import report
        report(run_dir(args))
    elif args.cmd == "rerank":
        from .rank import rerank_grading
        rerank_grading(Path(args.grading), check=args.check)
    elif args.cmd == "status":
        from .status import status
        status(run_dir(args), resolve(args))
    elif args.cmd == "run":
        from .ingest import ingest
        rd = run_dir(args)
        skip = set(filter(None, args.skip.split(",")))
        stages = [("ingest", lambda: ingest(Path(args.input), rd)), ("enrich", lambda: cmd_enrich(args)),
                  ("verify", lambda: cmd_verify(args)), ("group", lambda: cmd_group(args)),
                  ("rank", lambda: cmd_rank(args)), ("memo", lambda: cmd_memo(args)), ("export", lambda: cmd_export(args))]
        timings = {}
        t_all = time.time()
        for name, fn in stages:
            if name in skip:
                continue
            t0 = time.time()
            out = fn()
            timings[name] = round(time.time() - t0, 3)
            if name == "enrich" and out and out.get("pending_texts_after"):
                print(f"[run] enrichment incomplete ({out['pending_texts_after']:,} texts pending: {out['stop_reason']}). "
                      "Downstream stages run on completed records; rerun the same command to resume.")
        timings["end_to_end_wall_seconds"] = round(time.time() - t_all, 3)
        with (rd / "run_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "run_command", "at": time.time(), "stage_wall_seconds": timings}) + "\n")
        print("[run] stage wall seconds:", json.dumps(timings))
    else:
        globals()["cmd_" + args.cmd](args)


if __name__ == "__main__":
    main()
