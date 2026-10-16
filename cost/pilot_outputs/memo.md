# Decision memo: where Spotify's next quarter of product effort should go

**Recommendation: prioritise USABILITY.** Prioritize usability: free-tier ads and restricted track controls generate the most complaints and the highest severity volume.

Prioritize usability, which has 19 complaints [T1], a 37.3% share of all complaints [T4], and the highest severity sum at 51 [T2]. Within it, ads lead with 8 complaints [C5] and a severity sum of 21 [C6]. Premium gating of skip, back, and song selection overlaps with billing and should be scoped together with usability. Cancellation language is expressed intent only, with 3 usability records [T3].

## Recommended actions

### Reduce ad frequency and loudness for free-tier listeners
Ads are the largest usability issue by complaints [C5] and severity sum [C6], with reviews describing ads replacing songs and interrupting playback.

Issues: `usability.ads`

- `c2738a4f-e57c-46bc-a4ad-8ec5a4b5d5cd` (2022-07-02, `usability.ads`, severity 3): "wayy to many ads"
- `cf6166ae-d71a-4839-9add-088645ad3b78` (2023-02-09, `usability.ads`, severity 3): "always plays adds instead of songs"
- `ab67a772-c3b7-42ba-9b80-8d21d3857018` (2022-11-29, `usability.ads`, severity 2): "The ads are so loud :'("

### Restore skip, previous-track, and chosen-song controls for free users
This issue carries a mean severity of 3.000000 [C15] and a severity sum of 15 [C14], showing users feel locked out of basic playback control.

Issues: `usability.shuffle_or_track_control`, `billing.premium_paywall`

- `a3605554-5c3a-441d-836e-e9fdea83eb2e` (2023-10-31, `usability.shuffle_or_track_control`, severity 3): "The ability to skip a song or go to previous song has been removed from non subscribed users."
- `ebc64fe2-9553-4528-87d5-cb4bb9783be6` (2022-08-24, `usability.shuffle_or_track_control`, severity 3): "I CAN ONLY SKIP 6 OF THEM 6!!!"
- `d146397f-4a94-4980-be00-ae9212eca3a7` (2022-10-17, `billing.premium_paywall`, severity 3): "you can't even pick a certain song without Spotify premium"

### Review the home screen redesign and auto-playing audio elements
Redesign complaints total 4 [C17] with a severity sum of 9 [C18], and one review ties the issue to cancellation intent.

Issues: `usability.ui_redesign_or_navigation`

- `94c9f2f9-36fa-4c11-936e-660514fe7a35` (2023-03-19, `usability.ui_redesign_or_navigation`, severity 2): "the new homescreen update is horrible"
- `d455c11e-c530-4c03-a395-38f5a5cdb8d3` (2023-03-21, `usability.ui_redesign_or_navigation`, severity 2): "Rolling out big automatically playing audio elements,without any clear way to disable the automatic playing"
- `e16a4550-43e7-4ae1-b538-a65cc652c31b` (2023-10-15, `usability.ui_redesign_or_navigation`, severity 3): "Can't repeat and play specific part.please solve this matter. I'm leaving spotfy"

## Alternatives considered

- **billing/support**: Premium gating shows 6 complaints [T13] at a mean severity of 3.000000 [C11]; much of it overlaps with the usability track-control issue, so it is addressed in the same scope.
- **playback**: Playback has 7 complaints [T9] and a severity sum of 22 [T10], but it splits into crash [C25] and other [C29] issues with no single dominant cluster.
- **access**: Login failures total 2 complaints [T21] with a mean severity of 4.000000 [C23]; volume is small, so monitor rather than lead with it.
- **catalog/downloads**: Catalog has 4 complaints [T17] and downloads has 1 [T25], both below the usability and billing volumes.

## Limitations

- Reviews are self-selected public feedback and are not a representative user sample.
- The data contains no revenue, plan tier, or confirmed churn; cancellation language reflects expressed intent only.
- Coverage is 100 rows [X1] with 0 quarantined [X3], of which 51 are complaint or cancellation records [X5].
- Only 17 records were verified [X9] and 15 are flagged needs_review [X8], so classification confidence is moderate.
- Verifier topic and intent agreement were both 1.0 [X10][X11] on a small sample, with severity mean absolute error of 0.0588 [X12].
- The first and last months of the window are partial, which may distort trends.
- Coverage (code-written): 100 of 100 source rows completed; 0 quarantined (incl. 0 empty texts). Quarantined/pending rows are excluded from every count above.

## Claims used (computed by code from the full run; see claims.csv / claims_all.csv)

| claim | scope | issue/topic | metric | value |
|---|---|---|---|---|
| C5 | issue | `usability.ads` | complaint_count | 8 |
| C6 | issue | `usability.ads` | severity_sum | 21 |
| C11 | issue | `billing.premium_paywall` | mean_severity | 3.000000 |
| C14 | issue | `usability.shuffle_or_track_control` | severity_sum | 15 |
| C15 | issue | `usability.shuffle_or_track_control` | mean_severity | 3.000000 |
| C17 | issue | `usability.ui_redesign_or_navigation` | complaint_count | 4 |
| C18 | issue | `usability.ui_redesign_or_navigation` | severity_sum | 9 |
| C23 | issue | `access.login_failure` | mean_severity | 4.000000 |
| C25 | issue | `playback.crash_or_wont_open` | complaint_count | 2 |
| C29 | issue | `playback.playback_other` | complaint_count | 2 |
| T1 | topic | `usability` | complaint_count | 19 |
| T2 | topic | `usability` | severity_sum | 51 |
| T3 | topic | `usability` | cancellations | 3 |
| T4 | topic | `usability` | share_of_all_complaints_pct | 37.3 |
| T9 | topic | `playback` | complaint_count | 7 |
| T10 | topic | `playback` | severity_sum | 22 |
| T13 | topic | `billing` | complaint_count | 6 |
| T17 | topic | `catalog` | complaint_count | 4 |
| T21 | topic | `access` | complaint_count | 2 |
| T25 | topic | `downloads` | complaint_count | 1 |
| X1 | context | `` | rows_in_source | 100 |
| X3 | context | `` | quarantined_rows | 0 |
| X5 | context | `` | complaint_or_cancellation_records | 51 |
| X8 | context | `` | needs_review_records | 15 |
| X9 | context | `` | verified_sample_size | 17 |
| X10 | context | `` | verifier_topic_agreement | 1.0 |
| X11 | context | `` | verifier_intent_agreement | 1.0 |
| X12 | context | `` | verifier_severity_mae | 0.0588 |

_Written by the memo agent (anthropic:claude-haiku-5-5) from saved aggregates only; numbers, issue IDs and review IDs checked by code: PASS. A person reviewed the final argument before submission._
