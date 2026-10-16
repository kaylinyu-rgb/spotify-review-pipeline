# 100-review cost & runtime calculator

| command | what it does | paid? |
|---|---|---|
| `python cost/calculator.py` | **Default: offline replay.** Recomputes every cost from `pilot_calls.jsonl` usage × `rates.csv`, rebuilds `usage.csv`, `report.md`, `report.json` | no, and no key needed |
| `python cost/calculator.py --rate-multiplier 2` | arithmetic check: API $ doubles; measured time and local costs are unchanged | no |
| `python cost/calculator.py --rows 100000 --budget 10` | different projected volume or budget; measured pilot numbers unchanged | no |
| `python cost/calculator.py refresh --run runs/ckpt500 --label checkpoint_500` | adds a measured 500 / 10,000 checkpoint to `checkpoints.json` | no |
| `python cost/calculator.py pilot --confirm-paid` | **explicit paid pilot** on `data/cost_100.csv` (sha256 checked): empty result cache, 1 worker, full pipeline (enrich, declared 20% verify sample, group, rank, memo), then the warm rerun | yes, about 1 cent |

Importing or opening the calculator never makes calls. Files:

* `pilot_measurements.json`: input checksum, run IDs, settings, cold/warm wall-clock per stage, counts, cache hits
* `pilot_calls.jsonl`: every attempted call (cold and warm), with `run_phase`, `run_id`, request IDs, model, settings,
  `uncached_input_tokens` / `cached_input_tokens` / `cache_write_tokens` / `output_tokens` (mutually exclusive), and outcome
* `pilot_records.jsonl`: the 100 final records (grading-contract fields)
* `rates.csv`: editable prices with units, status (official / assumed / unknown), source URL and check date
* `usage.csv`: one line per call × billing item = units × price per unit (the mapping from charges to calls)
* `assumptions.json`: budget ($10/100k rows), workers/jobs, output cap, fallback cap, verify rate, base vs conservative scenarios
* `report.md`: measured table plus full-run projection (with and without exact-text reuse) and budget warnings

Cost formula: `item_cost = billed_units × price_per_unit` (per-1M prices are divided by 1,000,000), `total = Σ item_cost`.
Anthropic `input_tokens` already excludes cache reads and writes; OpenAI cached tokens are subtracted from input
before pricing. Thinking is disabled for enrichment; when enabled (fallback, memo) it is billed inside output
tokens and never added twice. Unknown prices (Jev) stay *unknown*.
