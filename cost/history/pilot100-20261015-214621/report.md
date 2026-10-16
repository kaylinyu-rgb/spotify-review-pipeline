# 100-review cost & runtime calculator report

Generated 2026-10-16 04:55:06 by `python cost/calculator.py` (offline replay of saved usage; rate multiplier 1.0).
Every API dollar below = billed units x price per unit from `cost/rates.csv`; itemised per call in `cost/usage.csv`.

## Measured: real 100-review pilot

- Input: `cost_100.csv` sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` (expected `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e`: MATCH), 100 IDs
- Run IDs: cold `pilot100-20261015-214621:cold`, warm `pilot100-20261015-214621:warm` (same run state, unchanged settings)
- Settings: `{"enrich": "anthropic:claude-haiku-5-5+effort-low+enrich-p2+schema-s2+entities-l1", "mode": "batch", "workers": 1, "batch_size": 50, "verify": "jev", "verify_rate": 0.2, "fallback": "claude-haiku-5-5"}`

| | cold (empty result cache) | warm (saved results) |
|---|---|---|
| input rows | 100 | 100 |
| completed | 100 | 100 |
| quarantined / failed | 0 | 0 |
| unique texts | 100 | 100 |
| texts sent to enrichment | 100 | 0 |
| result-cache hits (texts) | 0 | 100 |
| end-to-end wall-clock s | 338.207 | 3.551 |
| API spend (USD) | 0.005644 | 0.000000 |
| USD per 1,000 inputs | 0.056443 | 0.000000 |
| USD per completed record | 0.00005644 | 0.00000000 |
| throughput (rows/s, end to end) | 0.30 | 28.16 |
| calls with unknown cost | 1 | 1 |

### Stages (cold)

| stage | provider / model | label config | requests | failed | review IDs sent | uncached in | cached in | cache write | output | API USD | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enrich | anthropic-batch / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+effort-low+enrich-p2+schema-s2+entities-l1` | 2 | 0 | 100 | 4,519 | 3,780 | 3,780 | 6,286 | 0.002308 | 309.587 |
| verify | anthropic / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+verify-p1` | 1 | 1 | 17 | 0 | 0 | 0 | 0 | 0.000000 + unknown | 4.357 |
| group | anthropic / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+group-p1` | 2 | 1 | 46 | 3,430 | 682 | 682 | 2,164 | 0.001517 | 12.088 |
| memo | anthropic / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+memo-p1` | 1 | 0 | 15 | 6,335 | 0 | 1,360 | 2,032 | 0.001819 | 12.155 |
| rank (code) | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.008 |

### Stages (warm)

| stage | provider / model | label config | requests | failed | review IDs sent | uncached in | cached in | cache write | output | API USD | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enrich | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.003 |
| verify | anthropic / `claude-haiku-5-5` | `anthropic:claude-haiku-5-5+verify-p1` | 1 | 1 | 17 | 0 | 0 | 0 | 0 | 0.000000 + unknown | 3.528 |
| group | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.011 |
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
Measured basis: $0.00002308 enrichment per distinct text; 62.86 output tokens/text; enrichment failure rate 0.0; throughput 0.323 texts/s at 1 worker; verify $0.00000000/review; fallback $0.000434/review (rates x assumed tokens); fixed group+memo $0.003337 once (not multiplied by rows).

Controls: budget **$66.06** (course cap $10 per 100k rows), max workers 12, output cap 110 tokens/review + 200/request, fallback cap 0.10% of distinct texts, verify rate 1.0% (max 6000).

| scenario | reuse | texts sent | enrich $ | verify $ | fallback $ | fixed $ | total API $ | $/100k rows | enrich hours (modeled) | budget |
|---|---|---|---|---|---|---|---|---|---|---|
| base | with_exact_text_reuse | 484,189 | 11.40 | 0.00+unknown | 0.10 | 0.0033 | **11.51** | 1.74 | 3.5 | ok |
| base | no_reuse | 660,609 | 15.55 | 0.00+unknown | 0.14 | 0.0033 | **15.70** | 2.38 | 4.5 | ok |
| conservative | with_exact_text_reuse | 484,189 | 15.36 | 0.00+unknown | 0.21 | 0.0033 | **15.58** | 2.36 | 14.0 | ok |
| conservative | no_reuse | 660,609 | 20.96 | 0.00+unknown | 0.29 | 0.0033 | **21.25** | 3.22 | 20.0 | ok |

Scenario assumptions: base: {"retry_rate": 0.02, "fallback_fraction": 0.0005, "output_multiplier_on_cost": 1.0}; conservative: {"retry_rate": 0.1, "fallback_fraction": 0.001, "output_multiplier_on_cost": 1.25}

Hours (batch mode) are modeled as ceil(jobs / max in-flight jobs) x job turnaround, using the larger of the measured pilot turnaround (5.2 min) and the scenario assumption ({'base': 30, 'conservative': 120} min); the provider's SLA is < 24 h per job. Not measured; refresh after 500 and 10,000.

## Local compute (separate from API spend)

- unknown (laptop orchestrator; not metered). Kept separate from API spend; never folded into zero.

## Reproduce

```sh
python cost/calculator.py                       # offline replay (default)
python cost/calculator.py --rate-multiplier 2   # check: API $ doubles, time unchanged
python cost/calculator.py --rows 100000         # change projected volume; measured pilot unchanged
python cost/calculator.py pilot --confirm-paid  # explicit, paid: real cold+warm pilot
```
