# 100-review cost & runtime calculator report

Generated 2026-10-15 22:44:28 by `python cost/calculator.py` (offline replay of saved usage; rate multiplier 1.0).
Every API dollar below = billed units x price per unit from `cost/rates.csv`; itemised per call in `cost/usage.csv`.

## Measured: real 100-review pilot

- Input: `cost_100.csv` sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` (expected `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e`: MATCH), 100 IDs
- Run IDs: cold `pilot100-20261015-220758:cold`, warm `pilot100-20261015-220758:warm` (same run state, unchanged settings)
- Settings: `{"enrich": "anthropic:claude-haiku-5-5+effort-low+enrich-p2+schema-s2+entities-l1", "mode": "batch", "workers": 1, "batch_size": 50, "verify": "jev", "verify_rate": 0.2, "fallback": "claude-haiku-5-5"}`

| | cold (empty result cache) | warm (saved results) |
|---|---|---|
| input rows | 100 | 100 |
| completed | 100 | 100 |
| quarantined / failed | 0 | 0 |
| unique texts | 100 | 100 |
| texts sent to enrichment | 100 | 0 |
| result-cache hits (texts) | 0 | 100 |
| end-to-end wall-clock s | 480.067 | 0.027 |
| API spend (USD) | 0.007138 | 0.000000 |
| USD per 1,000 inputs | 0.071384 | 0.000000 |
| USD per completed record | 0.00007138 | 0.00000000 |
| throughput (rows/s, end to end) | 0.21 | 3703.70 |
| calls with unknown cost | 0 | 0 |

### Stages (cold)

| stage | provider / model | label config | requests | failed | review IDs sent | uncached in | cached in | cache write | output | API USD | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enrich | anthropic-batch / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+effort-low+enrich-p2+schema-s2+entities-l1` | 2 | 0 | 100 | 4,519 | 3,780 | 3,780 | 6,294 | 0.002310 | 448.439 |
| verify | anthropic / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+verify-p1` | 1 | 0 | 17 | 1,438 | 0 | 1,088 | 958 | 0.000759 | 4.006 |
| group | anthropic / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+group-p1` | 3 | 0 | 46 | 3,500 | 1,364 | 682 | 2,413 | 0.001655 | 12.775 |
| memo | anthropic / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+memo-p1` | 1 | 0 | 16 | 6,700 | 0 | 1,360 | 3,149 | 0.002414 | 14.831 |
| rank (code) | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.008 |

### Stages (warm)

| stage | provider / model | label config | requests | failed | review IDs sent | uncached in | cached in | cache write | output | API USD | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enrich | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.004 |
| verify | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.003 |
| group | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.009 |
| memo | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.004 |
| rank (code) | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.003 |

Batch size: enrichment <= 50 reviews/request (char cap 14,000); workers: 1 (pilot). Summed call durations are not used as wall time.

## Rates used (editable: `cost/rates.csv`)

| provider | model | item | price | unit | status | source | checked |
|---|---|---|---|---|---|---|---|
| anthropic | claude-haiku-5-5 | input | 0.10 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic | claude-haiku-5-5 | cached_input | 0.01 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic | claude-haiku-5-5 | cache_write | 0.125 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic | claude-haiku-5-5 | output | 0.50 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic | claude-sonnet-5-5 | input | 2.00 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic | claude-sonnet-5-5 | cached_input | 0.10 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic | claude-sonnet-5-5 | cache_write | 2.50 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic | claude-sonnet-5-5 | output | 10.00 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic-batch | claude-haiku-5-5 | input | 0.05 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic-batch | claude-haiku-5-5 | output | 0.25 | per_1M_tokens | official | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic-batch | claude-haiku-5-5 | cached_input | 0.01 | per_1M_tokens | assumed | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| anthropic-batch | claude-haiku-5-5 | cache_write | 0.125 | per_1M_tokens | assumed | https://platform.claude.com/docs/en/about-claude/pricing | 2026-10-15 |
| mock-batch | mock-keywords | input | 0 | per_1M_tokens | synthetic |  | 2026-10-15 |
| mock-batch | mock-keywords | output | 0 | per_1M_tokens | synthetic |  | 2026-10-15 |
| openai | gpt-6-luna | input | 0.10 | per_1M_tokens | official | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-15 |
| openai | gpt-6-luna | cached_input | 0.01 | per_1M_tokens | official | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-15 |
| openai | gpt-6-luna | cache_write | 0.125 | per_1M_tokens | official | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-15 |
| openai | gpt-6-luna | output | 0.50 | per_1M_tokens | official | https://developers.openai.com/api/docs/models/gpt-6-luna | 2026-10-15 |
| jev | jev-latest | input | UNKNOWN | per_1M_tokens | unknown | https://docs.typesafe.ai/api | 2026-10-15 |
| jev | jev-latest | output | UNKNOWN | per_1M_tokens | unknown | https://docs.typesafe.ai/api | 2026-10-15 |
| mock | mock-keywords | input | 0 | per_1M_tokens | synthetic |  | 2026-10-15 |
| mock | mock-keywords | output | 0 | per_1M_tokens | synthetic |  | 2026-10-15 |

## Full-run projection (estimates, not measurements)

Scope: 660,622 rows -> 660,609 nonempty classifications + 13 empty-text quarantines; 484,189 distinct texts with exact-text reuse.
Measured basis: $0.00002310 enrichment per distinct text; 62.94 output tokens/text; enrichment failure rate 0.0; throughput 0.223 texts/s at 1 worker; verify $0.00004464/review; fallback $0.000434/review (rates x assumed tokens); fixed group+memo $0.004070 once (not multiplied by rows).

Controls: budget **$66.06** (course cap $10 per 100k rows), max workers 12, output cap 110 tokens/review + 200/request, fallback cap 0.10% of distinct texts, verify rate 1.0% (max 6000).

| scenario | reuse | texts sent | enrich $ | verify $ | fallback $ | fixed $ | total API $ | $/100k rows | enrich hours (modeled) | budget |
|---|---|---|---|---|---|---|---|---|---|---|
| base | with_exact_text_reuse | 484,189 | 11.41 | 0.22 | 0.10 | 0.0041 | **11.73** | 1.78 | 3.5 | ok |
| base | no_reuse | 660,609 | 15.56 | 0.27 | 0.14 | 0.0041 | **15.98** | 2.42 | 4.5 | ok |
| conservative | with_exact_text_reuse | 484,189 | 15.38 | 0.22 | 0.21 | 0.0041 | **15.81** | 2.39 | 14.0 | ok |
| conservative | no_reuse | 660,609 | 20.98 | 0.27 | 0.29 | 0.0041 | **21.54** | 3.26 | 20.0 | ok |

Scenario assumptions: base: {"retry_rate": 0.02, "fallback_fraction": 0.0005, "output_multiplier_on_cost": 1.0}; conservative: {"retry_rate": 0.1, "fallback_fraction": 0.001, "output_multiplier_on_cost": 1.25}

Hours (batch mode) are modeled as ceil(jobs / max in-flight jobs) x job turnaround, using the larger of the measured pilot turnaround (7.5 min) and the scenario assumption ({'base': 30, 'conservative': 120} min); the provider's SLA is < 24 h per job. Not measured; refresh after 500 and 10,000.

## Local compute (separate from API spend)

- unknown (laptop orchestrator; not metered). Kept separate from API spend; never folded into zero.

## Refreshed estimates from larger checkpoints (measured on those runs)

| checkpoint | rows | distinct texts | enrich calls | failed | enrich $ | $/distinct text | texts/s | workers | projected full $ (reuse) |
|---|---|---|---|---|---|---|---|---|---|
| checkpoint_500 | 500 | 479 | 11 | 0 | 0.0099 | 0.00002063 | 0.68 | 1 | 9.99 |
| analysis_10000 | 10,000 | 8,448 | 171 | 0 | 0.1618 | 0.00001915 | 14.33 | 1 | 9.27 |

## Reproduce

```sh
python cost/calculator.py                       # offline replay (default)
python cost/calculator.py --rate-multiplier 2   # check: API $ doubles, time unchanged
python cost/calculator.py --rows 100000         # change projected volume; measured pilot unchanged
python cost/calculator.py pilot --confirm-paid  # explicit, paid: real cold+warm pilot
```
