# Shared labels, examples and output schema

The exact model instructions are versioned in [`pipeline/prompts/`](../pipeline/prompts/); allowed values are
defined once in [`pipeline/config.py`](../pipeline/config.py) and enforced by code.

## Primary topics (grading contract, exact)

| topic | definition | optional subtopics (`issue_id = topic.subtopic`) |
|---|---|---|
| `access` | Login, signup, password or account access | login_failure, logged_out_or_account_lost, account_hacked, signup_or_install, access_other |
| `usability` | Navigation, controls, layout, queue/playlist management, ad interruptions | ads, shuffle_or_track_control, ui_redesign_or_navigation, playlist_or_library, usability_other |
| `playback` | Playback failure, crashes, lag, connection failures, audio quality, resource use | crash_or_wont_open, playback_stops_or_skips, device_or_connection, audio_quality, performance_or_battery, playback_other |
| `downloads` | Downloading, saved music, offline listening, disappearing downloads | download_fails, downloads_disappear, offline_mode, downloads_other |
| `catalog` | Missing songs/artists, search/discovery, recommendations, lyrics availability | missing_or_removed_content, search_or_discovery, recommendations, lyrics, podcasts_or_audiobooks, catalog_other |
| `billing` | Price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls | premium_paywall, price, charge_or_cancel_problem, premium_not_recognized, billing_other |
| `support` | Contacting support and the support response | support_unhelpful_or_unreachable, support_other |
| `other` | General praise/criticism, unrelated content, or no supported specific topic | general_praise, general_criticism, unrelated_or_unclear, other_specific |

Rules: highest supported severity first, then the first specific problem mentioned; for praise the first
specific praised feature (generic praise → `other`); a paid-plan mention alone is not `billing`; a
subscription that fails to activate is `billing`; music crashing for a paying user is `playback`.

## Intent (precedence order)

`cancellation` (explicitly leaving / uninstalling / cancelling / threatening to) → `complaint` (negative,
incl. mixed) → `request` (desired change, no failure) → `praise` → `unclear` (meaningless, unrelated, bare
boycott slogan). Generic "bad app" is a complaint about `other.general_criticism`.

## Severity (shared scale)

| sev | meaning | our examples (illustrative, not golden-set texts) |
|---|---|---|
| 1 | No reported problem: praise, neutral/unclear, pure feature request | "Love it"; "Please add a sleep timer"; "#BoycottX" |
| 2 | Dislike, generic criticism, minor annoyance, cosmetic; no functional loss | "Worst app ever"; "Uninstalling, the new update is ugly" (cancellation, sev 2) |
| 3 | Degraded / restricted function; some use or workaround remains | "An ad after every two songs"; "Only 6 skips without premium"; "Lyrics now need premium" |
| 4 | Clearly blocked core task | "App keeps crashing when I open it, can't listen at all"; "Can't log in" |
| 5 | Explicit serious financial, privacy or data harm | "Charged twice after I cancelled, no refund"; "Account hacked, email changed"; "Logged out and all 1300 liked songs are gone" |

Stars, swearing, capitals or cancellation intent alone never raise severity; stars are never sent to the model.

## Sentiment

One of −1, −0.5, 0, 0.5, 1 (strongly negative … strongly positive). Golden-set tolerance is predeclared as ±0.5.

## Evidence quote, entities, needs_review

* `evidence_quote`: the model copies an exact substring (≤ 12 words). Code accepts it only if it is a substring
  of the original text; a whitespace/curly-quote/case slip is repaired by slicing the original; otherwise a
  review ≤ 300 chars uses its full text and is flagged `needs_review`; a longer review fails validation (retry).
* `entities`: **code**, not the model: explicit feature terms from a fixed lexicon (`pipeline/entities.py`)
  matched in the text, so entities can never be unsupported additions.
* `needs_review`: model flag (ambiguous, sarcasm, missing context, unreadable language, embedded instructions)
  OR a code flag (quote replaced). It is evaluated as a prediction against the human `needs_review` column.

## Output schema

Model output per request (JSON schema enforced by the provider's structured outputs, then re-validated in code):

```json
{"results": [{"k": "r01", "label": "billing.premium_paywall", "intent": "complaint", "sev": 3, "sent": -0.5,
              "quote": "only 6 skips", "flag": false}]}
```

`k` is a short per-request key (r01..r50) that code maps back to the source `review_id` (cuts output tokens;
missing, duplicate or foreign keys are rejected). Final record (grading contract):

```json
{"review_id": "…", "source_sha256": "…", "status": "completed", "topic": "billing", "intent": "complaint",
 "sentiment": -0.5, "severity": 3, "entities": ["premium", "skip limit"], "evidence_quote": "only 6 skips",
 "needs_review": false, "label_config": "anthropic:claude-haiku-5-5+effort-low+enrich-p2+schema-s2+entities-l1",
 "cache_source_id": "…only for exact-text reuse…"}
```
