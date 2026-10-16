"""Stage 4 - GROUP (code: stable membership; model role: issue-naming agent).

Membership is deterministic: every completed complaint/cancellation record joins
exactly one issue, issue_id = "<topic>.<subtopic>" from its enrichment label.
A small model only writes human-readable names from a bounded evidence sample;
it cannot move reviews, so ranking never depends on a model call.
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
import uuid
from collections import defaultdict
from pathlib import Path

from . import providers
from .config import DEFAULTS, GROUP_PROMPT_VERSION, read_prompt
from .rates import cost, load_rates
from .records import build_records, write_jsonl_gz
from .store import Store

SAMPLE_PER_ISSUE = 8
ISSUES_PER_CALL = 12


def materialize(run_dir: Path, enrich_cfg) -> dict:
    """Saved handoff from enrichment: enriched.jsonl.gz (all rows) + quarantine.jsonl."""
    recs = list(build_records(run_dir, enrich_cfg))
    write_jsonl_gz(run_dir / "enriched.jsonl.gz", recs)
    with (run_dir / "quarantine.jsonl").open("w", encoding="utf-8") as f:
        for r in recs:
            if r["status"] == "quarantined":
                f.write(json.dumps({"review_id": r["review_id"], "source_sha256": r["source_sha256"], "reason": r["reason"],
                                    "attempts": r.get("x_attempts", 0), "detail": r.get("x_detail")}, ensure_ascii=False) + "\n")
    return {r["review_id"]: r for r in recs}


def _schema():
    item = {"type": "object", "additionalProperties": False, "required": ["issue_id", "title", "description", "example_review_ids"],
            "properties": {"issue_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"},
                           "example_review_ids": {"type": "array", "items": {"type": "string"}}}}
    return {"type": "object", "additionalProperties": False, "required": ["issues"],
            "properties": {"issues": {"type": "array", "items": item}}}


def _fallback_title(iid):
    t, s = iid.split(".", 1)
    return f"{t.title()}: {s.replace('_', ' ')}"


def group(run_dir: Path, enrich_cfg, provider: str, model: str | None = None) -> dict:
    t0 = time.time()
    recs = materialize(run_dir, enrich_cfg)
    members = defaultdict(list)
    for r in recs.values():
        if r["status"] == "completed" and r["intent"] in ("complaint", "cancellation"):
            members[r["x_label"]].append(r)
    with (run_dir / "membership.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["issue_id", "review_id"])
        for iid in sorted(members):
            for r in members[iid]:
                w.writerow([iid, r["review_id"]])
    # bounded evidence sample per issue (deterministic; originals only, prefer informative quotes)
    packs = []
    for iid in sorted(members, key=lambda i: -sum(r["severity"] for r in members[i])):
        origs = [r for r in members[iid] if "cache_source_id" not in r and len(r["evidence_quote"]) >= 15]
        origs.sort(key=lambda r: hashlib.sha256(("group-sample:" + r["review_id"]).encode()).hexdigest())
        sample = [{"review_id": r["review_id"], "quote": r["evidence_quote"][:200]} for r in origs[:SAMPLE_PER_ISSUE]]
        n = len(members[iid])
        sev = sum(r["severity"] for r in members[iid])
        packs.append({"issue_id": iid, "member_count": n, "mean_severity": round(sev / n, 3), "sample": sample})

    store = Store(run_dir / "state.sqlite")
    model = model or {"anthropic": DEFAULTS["group_model"], "openai": "gpt-6-luna", "mock": "mock-keywords"}[provider]
    prov = providers.make(provider, model, "low" if provider == "anthropic" else "none")
    rates = load_rates()
    key = hashlib.sha256(json.dumps([packs, provider, model, GROUP_PROMPT_VERSION]).encode()).hexdigest()
    cached = store.get_meta("group_cache:" + key)
    names, calls = {}, 0
    if cached:
        names = cached
        print("[group] issue names reused from cache (same membership/sample/model/prompt): 0 new calls")
    else:
        system = read_prompt(f"{GROUP_PROMPT_VERSION}.md")
        for i in range(0, len(packs), ISSUES_PER_CALL):
            chunk = packs[i:i + ISSUES_PER_CALL]
            allowed = {p["issue_id"]: {s["review_id"] for s in p["sample"]} for p in chunk}
            ids = [s["review_id"] for p in chunk for s in p["sample"]]
            user = "Name these issues.\n" + json.dumps(chunk, ensure_ascii=False)
            t = time.time()
            rid, outcome, err, usage = "grp-" + uuid.uuid4().hex[:14], "failed", None, {}
            try:
                if provider == "mock":
                    out = {"issues": [{"issue_id": p["issue_id"], "title": _fallback_title(p["issue_id"]),
                                       "description": "Mock description.", "example_review_ids": [s["review_id"] for s in p["sample"][:2]]} for p in chunk]}
                    usage = {"input": len(user) // 4, "output": 40 * len(chunk)}
                else:
                    res = prov.complete(system, user, _schema(), 120 * len(chunk) + 200)
                    usage = res.usage
                    out = json.loads(res.text)
                for o in out["issues"]:
                    iid = o.get("issue_id")
                    if iid not in allowed:
                        continue  # reject new / foreign issues
                    ex = [x for x in o.get("example_review_ids", []) if x in allowed[iid]][:3]  # reject foreign ids
                    names[iid] = {"title": str(o.get("title", ""))[:80] or _fallback_title(iid),
                                  "description": str(o.get("description", ""))[:300], "example_review_ids": ex,
                                  "named_by": f"{provider}:{model}"}
                outcome = "succeeded"
            except (providers.TransportError, ValueError, KeyError, TypeError) as e:
                err = str(e)[:200]
            c, _ = cost(prov.name, model, usage, rates)
            store.begin()
            store.log_call({"request_id": rid, "role": "group", "review_ids": ids, "model": model, "provider": prov.name,
                            "label_config": f"{provider}:{model}+{GROUP_PROMPT_VERSION}", "phase": "group", "outcome": outcome,
                            "error": err, "input_tokens": usage.get("input", 0), "cached_input_tokens": usage.get("cached_input", 0),
                            "cache_write_tokens": usage.get("cache_write", 0), "output_tokens": usage.get("output", 0),
                            "usage_known": int(bool(usage)), "cost_usd": c, "started_at": t, "ended_at": time.time(),
                            "duration_s": round(time.time() - t, 3), "attempt": 1, "session_id": "group", "settings": prov.settings()})
            store.commit()
            calls += 1
        store.set_meta("group_cache:" + key, names)
    issues = []
    for p in packs:
        nm = names.get(p["issue_id"]) or {"title": _fallback_title(p["issue_id"]), "description": "", "example_review_ids": [],
                                          "named_by": "code_fallback"}
        issues.append({**p, **nm, "topic": p["issue_id"].split(".")[0]})
    (run_dir / "issues.json").write_text(json.dumps(issues, indent=2, ensure_ascii=False) + "\n")
    n_mem = sum(len(v) for v in members.values())
    print(f"[group] {len(members)} issues, {n_mem:,} complaint/cancellation memberships, {calls} naming calls, "
          f"{time.time() - t0:.1f}s")
    with (run_dir / "run_log.jsonl").open("a") as f:
        f.write(json.dumps({"event": "group", "issues": len(members), "memberships": n_mem, "calls": calls,
                            "seconds": round(time.time() - t0, 2)}) + "\n")
    return {"issues": len(members), "memberships": n_mem, "calls": calls}
