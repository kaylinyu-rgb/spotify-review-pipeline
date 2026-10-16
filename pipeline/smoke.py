"""Paid smoke test (~$0.001): 3 short dev reviews through the real enrichment request shape, plus one
batch-API submission check if --mode batch. Verifies key, model ID, structured-output schema and parsing
before any real spend. Writes nothing to a run."""
from __future__ import annotations

import json
import time

from . import providers
from .enrich import build_user, enrich_schema, system_prompt, validate_item

SAMPLES = ["Too many ads, I get one after every song now",
           "App crashes every time I open it on my phone",
           "Love the daily mixes!"]


def smoke(provider, model, effort, mode="sync"):
    p = providers.make(provider, model, effort)
    batch = [{"rep_id": f"smoke-{i}", "rep_text": t} for i, t in enumerate(SAMPLES)]
    t0 = time.time()
    try:
        r = p.complete(system_prompt(), build_user(batch), enrich_schema(), 600)
    except providers.TransportError as e:
        raise SystemExit(f"[smoke] FAILED: {e}")
    print(f"[smoke] {provider}:{model} ok in {time.time() - t0:.1f}s stop={r.stop_reason} usage={r.usage}")
    out = json.loads(r.text)["results"]
    keys = {f"r{i + 1:02d}": t for i, t in enumerate(SAMPLES)}
    for it in out:
        rec, err = validate_item(it, keys.get(it.get("k"), ""))
        print("  ", it.get("k"), "->", err or f"{rec['label']} / {rec['intent']} / sev {rec['severity']} / quote “{rec['evidence_quote']}”")
    if mode == "batch" and provider == "anthropic":
        b = providers.make("anthropic-batch", model, effort)
        resp = b.submit([{"custom_id": "smoke1", "params": b.params(system_prompt(), build_user(batch[:1]), enrich_schema(), 300)}])
        print(f"[smoke] batch API accepted job {resp.get('id')} ({resp.get('processing_status')}); it will finish on its own (cost < $0.001).")
