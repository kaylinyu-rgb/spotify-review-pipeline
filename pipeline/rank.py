"""Stage 5 - RANK (code only, never calls a model).

priority(issue) = complaint_count x mean_severity == severity_sum (integer arithmetic).
Order: descending score, then ascending issue_id. Means: 6 decimals, half-up.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .records import read_jsonl

RANK_FIELDS = ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"]


def mean6(total: int, n: int) -> str:
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def compute_ranking(records: dict, membership: list[tuple[str, str]]) -> list[dict]:
    sev = defaultdict(list)
    seen = set()
    for iid, rid in membership:
        if (iid, rid) in seen:
            raise ValueError(f"duplicate membership {(iid, rid)}")
        seen.add((iid, rid))
        r = records[rid]
        if r.get("status") != "completed" or r["intent"] not in ("complaint", "cancellation"):
            raise ValueError(f"non-complaint in membership: {rid}")
        sev[iid].append(r["severity"])
    rows = [{"issue_id": i, "complaint_count": len(v), "severity_sum": sum(v), "mean_severity": mean6(sum(v), len(v)),
             "priority_score": sum(v)} for i, v in sev.items()]
    rows.sort(key=lambda x: (-x["priority_score"], x["issue_id"]))
    for k, r in enumerate(rows, 1):
        r["rank"] = k
    return rows


def write_ranking(path: Path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RANK_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: str(r[k]) for k in RANK_FIELDS})


def read_membership(path: Path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [(r["issue_id"], r["review_id"]) for r in csv.DictReader(f)]


def rank_run(run_dir: Path) -> list[dict]:
    """Rank from the run's saved handoffs: enriched.jsonl.gz + membership.csv."""
    recs = {r["review_id"]: r for r in read_jsonl(run_dir / "enriched.jsonl")}
    mem = read_membership(run_dir / "membership.csv")
    rows = compute_ranking(recs, mem)
    write_ranking(run_dir / "ranking.csv", rows)
    write_aggregates(run_dir, recs, mem, rows)
    print(f"[rank] {len(rows)} issues ranked from {len(mem):,} memberships (no model calls). Top 5:")
    for r in rows[:5]:
        print(f"   {r['rank']:>2}. {r['issue_id']:<45} n={r['complaint_count']:>7,} mean={r['mean_severity']} score={r['priority_score']:,}")
    return rows


def write_aggregates(run_dir: Path, recs: dict, mem, ranking):
    """Extra code-computed tables for the memo and dashboard (clearly separate from the baseline)."""
    issue_of = {rid: iid for iid, rid in mem}
    topic = defaultdict(Counter)
    monthly = defaultdict(Counter)
    issue_extra = defaultdict(Counter)
    totals = Counter()
    for r in recs.values():
        totals["rows"] += 1
        m = (r.get("x_timestamp") or "")[:7]
        monthly[m]["rows"] += 1
        if r["status"] != "completed":
            totals["quarantined"] += 1
            totals["quarantine:" + r["reason"]] += 1
            continue
        totals["completed"] += 1
        totals["cache_reuse"] += "cache_source_id" in r
        totals["needs_review"] += r["needs_review"]
        totals["intent:" + r["intent"]] += 1
        monthly[m]["completed"] += 1
        t = topic[r["topic"]]
        t["reviews"] += 1
        t["intent:" + r["intent"]] += 1
        if r["intent"] in ("complaint", "cancellation"):
            t["complaint_count"] += 1
            t["severity_sum"] += r["severity"]
            t["cancellations"] += r["intent"] == "cancellation"
            t[f"sev{r['severity']}"] += 1
            monthly[m]["complaints"] += 1
            monthly[m]["complaints:" + r["topic"]] += 1
            e = issue_extra[issue_of[r["review_id"]]]
            e["cancellations"] += r["intent"] == "cancellation"
            e["needs_review"] += r["needs_review"]
            e["sev4plus"] += r["severity"] >= 4
            e["rating_1"] += r.get("x_rating") == "1"
    with (run_dir / "aggregates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(RANK_FIELDS + ["topic", "cancellations", "severity_4_or_5", "needs_review", "one_star"])
        for r in ranking:
            e = issue_extra[r["issue_id"]]
            w.writerow([r[k] for k in RANK_FIELDS] + [r["issue_id"].split(".")[0], e["cancellations"], e["sev4plus"],
                                                      e["needs_review"], e["rating_1"]])
    with (run_dir / "topic_aggregates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["topic", "completed_reviews", "complaint_count", "severity_sum", "mean_severity", "cancellations",
                    "sev1", "sev2", "sev3", "sev4", "sev5", "praise", "request", "unclear"])
        for tname, t in sorted(topic.items(), key=lambda kv: -kv[1]["severity_sum"]):
            w.writerow([tname, t["reviews"], t["complaint_count"], t["severity_sum"],
                        mean6(t["severity_sum"], t["complaint_count"]) if t["complaint_count"] else "",
                        t["cancellations"], *[t[f"sev{i}"] for i in range(1, 6)], t["intent:praise"], t["intent:request"],
                        t["intent:unclear"]])
    topics = sorted(topic)
    with (run_dir / "monthly_trends.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "rows", "completed", "complaints"] + [f"complaints_{t}" for t in topics])
        for m in sorted(monthly):
            c = monthly[m]
            w.writerow([m, c["rows"], c["completed"], c["complaints"]] + [c["complaints:" + t] for t in topics])
    (run_dir / "totals.json").write_text(json.dumps(dict(totals), indent=2, sort_keys=True) + "\n")


def rerank_grading(folder: Path, check: bool = False):
    """Regenerate ranking.csv from grading/records.jsonl(.gz) + membership.csv, with no model calls."""
    recs = {r["review_id"]: r for r in read_jsonl(folder / "records.jsonl")}
    rows = compute_ranking(recs, read_membership(folder / "membership.csv"))
    target = folder / ("ranking.recomputed.csv" if check else "ranking.csv")
    write_ranking(target, rows)
    if check:
        same = (folder / "ranking.csv").read_text() == target.read_text()
        print(f"[rerank] recomputed {len(rows)} issues -> {target.name}; identical to saved ranking.csv: {same}")
        target.unlink()
        if not same:
            raise SystemExit(1)
    else:
        print(f"[rerank] wrote {target} ({len(rows)} issues)")
