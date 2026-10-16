# Decision memo: where Spotify's next quarter of product effort should go

**Recommendation: prioritise BILLING/SUPPORT.** Prioritize billing/support: premium gating of basic features drives the largest billing complaint load and expressed cancellation intent.

The billing topic has 50,397 complaints [T9], 17.1% of all complaints [T12], and 9,552 cancellation-intent records [T11], the highest cancellation count of any topic. Within billing, the premium paywall issue has 41,553 complaints [C5] and a severity sum of 115,758 [C6]. Usability has more total complaints (77,884 [T1]) but is split across ads, controls and navigation, so a single fix would reach less of it.

## Recommended actions

### Review which basic features sit behind premium
Users say core features like shuffle and song selection are locked, which is the paywall issue with 41,553 complaints [C5]. A clear audit of free-tier features would show where gating is causing the complaints.

Issues: `billing.premium_paywall`

- `5d8c1d43-78b5-4087-b409-1a4dc1adc572` (2023-10-09, `billing.premium_paywall`, severity 3): "all the basic features of a music player app locked behind premium"
- `dc18ffbc-f0d8-4cce-a193-a28a801f6aa9` (2023-11-15, `billing.premium_paywall`, severity 3): "This app is only for premium users only"

### Add clearer free-tier messaging and support paths for paywall questions
Reviews describe the app as premium-only, and billing support complaints are tracked separately at 586 [T29]. Clearer messaging before users hit a paywall could reduce complaints without changing the pricing model.

Issues: `billing.premium_paywall`

- `4cd090df-2c51-484b-a989-7956da52ece0` (2023-10-20, `billing.premium_paywall`, severity 2): "It only asks for their premium"

## Alternatives considered

- **usability**: Usability has the most complaints at 77,884 [T1], but it is split across ads 37,172 [C9], shuffle and track control 19,039 [C13] and navigation 14,052 [C17], so no single fix covers it.
- **playback**: Playback stops or skips has 10,266 complaints [C21] with a severity sum of 31,365 [C22], but the playback topic has only 2,466 cancellation-intent records [T15].
- **access**: Login failure has high mean severity at 3.887905 [C31], but only 6,887 complaints [C29], which is a smaller and narrower group.

## Limitations

- Reviews are self-selected public posts, so they do not represent the full user base.
- The data has no revenue, plan tier, or confirmed churn; cancellation records are expressed intent only.
- 96,340 records need review [X8] and the verifier's topic agreement is 0.8524 [X10], so issue-level counts carry classification uncertainty.
- Quoted reviews are illustrative examples and do not measure how common each complaint is.
- Coverage (code-written): 660,602 of 660,622 source rows completed; 20 quarantined (incl. 13 empty texts). Quarantined/pending rows are excluded from every count above.

## Claims used (computed by code from the full run; see claims.csv / claims_all.csv)

| claim | scope | issue/topic | metric | value |
|---|---|---|---|---|
| C5 | issue | `billing.premium_paywall` | complaint_count | 41553 |
| C6 | issue | `billing.premium_paywall` | severity_sum | 115758 |
| C9 | issue | `usability.ads` | complaint_count | 37172 |
| C13 | issue | `usability.shuffle_or_track_control` | complaint_count | 19039 |
| C17 | issue | `usability.ui_redesign_or_navigation` | complaint_count | 14052 |
| C21 | issue | `playback.playback_stops_or_skips` | complaint_count | 10266 |
| C22 | issue | `playback.playback_stops_or_skips` | severity_sum | 31365 |
| C29 | issue | `access.login_failure` | complaint_count | 6887 |
| C31 | issue | `access.login_failure` | mean_severity | 3.887905 |
| T1 | topic | `usability` | complaint_count | 77884 |
| T9 | topic | `billing` | complaint_count | 50397 |
| T11 | topic | `billing` | cancellations | 9552 |
| T12 | topic | `billing` | share_of_all_complaints_pct | 17.1 |
| T15 | topic | `playback` | cancellations | 2466 |
| T29 | topic | `support` | complaint_count | 586 |
| X8 | context | `` | needs_review_records | 96340 |
| X10 | context | `` | verifier_topic_agreement | 0.8524 |

_Written by the memo agent (anthropic:claude-haiku-5-5) from saved aggregates only; numbers, issue IDs and review IDs checked by code: PASS. I, Kaylin, reviewed the final argument before submission._
