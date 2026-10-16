# Decision memo: where Spotify's next quarter of product effort should go

**Recommendation: prioritise USABILITY.** Prioritize usability: shuffle/track control and ad interruptions carry the most complaint weight, though verification is absent.

Usability has the largest topic complaint count, 20 [T1], and a share of 39.2% of all complaints [T4], with the highest priority scores among top issues. Within it, shuffle or track control scores 21 [C8] and ads score 19 [C12]. Start with these two issues, and treat the results as directional because no verifier sample was run [X9] and 17 records still need review [X8].

## Recommended actions

### Fix shuffle and track-control behavior in playlists and single-track playback
This issue has 7 complaints [C5] and a severity sum of 21 [C6], the highest severity total among the top issues. Reviews describe random playlist order and an inability to go back a few seconds.

Issues: `usability.shuffle_or_track_control`

- `5c9c17d3-9d6a-4fa1-a2a4-ae98eefbbd25` (2023-10-12, `usability.shuffle_or_track_control`, severity 3): "it plays any song of the Playlist randomly"
- `9e5f9745-f8be-48d3-b9de-4d118507d94a` (2023-10-28, `usability.shuffle_or_track_control`, severity 3): "We can't even go back few second to play music?"

### Reduce ad frequency and ad placement between tracks for free-tier users
Ads show 8 complaints [C9] with a severity sum of 19 [C10]. Reviews describe ads appearing every one or two songs, which makes the product feel unusable.

Issues: `usability.ads`

- `cf6166ae-d71a-4839-9add-088645ad3b78` (2023-02-09, `usability.ads`, severity 3): "that always plays adds instead of songs"
- `3e8bdc92-4934-457e-85cc-8b9d14bf51c0` (2023-11-03, `usability.ads`, severity 3): "it's always every 1 or 2 song then instant ads"

### Validate the usability findings with a manual sample before committing the quarter
Zero records have been verified [X9], and 17 records are flagged for review [X8]. A targeted check of the top usability items would confirm the ranking before major investment.

Issues: `usability.shuffle_or_track_control`, `usability.ads`


## Alternatives considered

- **billing/support**: Billing has 5 complaints [T13] with a severity sum of 14 [T14], and the premium paywall issue has 4 complaints [C13]. Its volume is well below usability, and the paywall complaints overlap with the premium-gated controls already covered under usability.
- **playback**: Playback has 7 complaints [T9], close to usability in count but with a severity sum of 22 [T10]. Its top issue, crash or won't open, has only 2 complaints [C21], so the signal is concentrated in fewer reports.
- **access**: Access has only 2 complaints [T21] and a share of 3.9% [T24]. The login failure issue is small in volume, though its mean severity is 4.000000 [C19], so it is worth monitoring.

## Limitations

- The data is self-selected public reviews from May 2022 to November 2023 [X1] and does not represent all users.
- The dataset contains no revenue, plan tier, or confirmed churn; cancellation language reflects expressed intent only, with 8 cancellation-intent records [X6].
- No verifier sample was run and no agreement or error metrics are available [X9][X10][X11][X12].
- 17 records still need review [X8], so classifications may shift.
- Quotes are short excerpts and may not capture full context.
- Coverage (code-written): 100 of 100 source rows completed; 0 quarantined (incl. 0 empty texts). Quarantined/pending rows are excluded from every count above.

## Claims used (computed by code from the full run; see claims.csv / claims_all.csv)

| claim | scope | issue/topic | metric | value |
|---|---|---|---|---|
| C5 | issue | `usability.shuffle_or_track_control` | complaint_count | 7 |
| C6 | issue | `usability.shuffle_or_track_control` | severity_sum | 21 |
| C8 | issue | `usability.shuffle_or_track_control` | priority_score | 21 |
| C9 | issue | `usability.ads` | complaint_count | 8 |
| C10 | issue | `usability.ads` | severity_sum | 19 |
| C12 | issue | `usability.ads` | priority_score | 19 |
| C13 | issue | `billing.premium_paywall` | complaint_count | 4 |
| C19 | issue | `access.login_failure` | mean_severity | 4.000000 |
| C21 | issue | `playback.crash_or_wont_open` | complaint_count | 2 |
| T1 | topic | `usability` | complaint_count | 20 |
| T4 | topic | `usability` | share_of_all_complaints_pct | 39.2 |
| T9 | topic | `playback` | complaint_count | 7 |
| T10 | topic | `playback` | severity_sum | 22 |
| T13 | topic | `billing` | complaint_count | 5 |
| T14 | topic | `billing` | severity_sum | 14 |
| T21 | topic | `access` | complaint_count | 2 |
| T24 | topic | `access` | share_of_all_complaints_pct | 3.9 |
| X1 | context | `` | rows_in_source | 100 |
| X6 | context | `` | cancellation_intent_records | 8 |
| X8 | context | `` | needs_review_records | 17 |
| X9 | context | `` | verified_sample_size | 0 |
| X10 | context | `` | verifier_topic_agreement | None |
| X11 | context | `` | verifier_intent_agreement | None |
| X12 | context | `` | verifier_severity_mae | None |

_Written by the memo agent (anthropic:claude-haiku-5-5) from saved aggregates only; numbers, issue IDs and review IDs checked by code: PASS. A person reviewed the final argument before submission._
