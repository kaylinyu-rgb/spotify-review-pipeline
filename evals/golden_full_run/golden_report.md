# Golden-set evaluation (50 human labels vs saved predictions)

Run `full`, label_config `anthropic:claude-haiku-5-5+effort-low+enrich-p2+schema-s2+entities-l1`. Valid predictions 50/50; ambiguous (human-marked) 0.

| metric | value |
|---|---|
| topic_accepting_alternatives agreement | 0.48 |
| topic_exact agreement | 0.48 |
| intent agreement | 0.84 |
| severity_exact agreement | 0.62 |
| sentiment_within_0.5 agreement | 1.0 |
| all_three agreement | 0.26 |
| needs_review_match agreement | 0.82 |
| severity MAE | 0.52 |
| sentiment MAE | 0.12 |
| evidence quote exact-substring rate | 1.0 |
| topic macro-F1 | 0.34 |
| intent macro-F1 | 0.705 |

## Topic confusion (human → predicted)

| human | predicted | n |
|---|---|---|
| catalog | catalog | 1 |
| catalog | other | 1 |
| other | billing | 2 |
| other | catalog | 3 |
| other | other | 14 |
| other | usability | 1 |
| support | playback | 1 |
| usability | access | 1 |
| usability | billing | 2 |
| usability | catalog | 2 |
| usability | downloads | 1 |
| usability | other | 10 |
| usability | playback | 2 |
| usability | usability | 9 |

## Disagreements (37)

| review_id | text | human t/i/s | model t/i/s | fields |
|---|---|---|---|---|
| `292ce26a` | Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks  | other/unclear/4 | catalog/complaint/3 | topic,intent,severity |
| `a70e8d3e` | Great app use it every chance I get | usability/praise/1 | other/praise/1 | topic |
| `0d4f8b48` | It's really an amazing experience with Spotify...I love it🥰 | usability/praise/1 | other/praise/1 | topic |
| `599a0d41` | I just loved it | usability/praise/1 | other/praise/1 | topic |
| `1fc8b08f` | Duo Premium .... No ads at all! | other/praise/1 | billing/praise/1 | topic |
| `947821dc` | Very good but wen I play my song it o ly plays a little bit then it stops I updated my pho | usability/complaint/3 | playback/complaint/3 | topic |
| `723f07de` | Update: I reached out to Spotify Support and with some help from Sarah I was able to get t | support/request/3 | playback/complaint/3 | topic,intent |
| `47428620` | This app is bad work | usability/complaint/2 | other/complaint/2 | topic |
| `01d453b0` | I like it but god I hate it when the music Interrupts my ads | usability/complaint/3 | usability/complaint/2 | severity |
| `ac6cd66d` | Lhat ng song nasa spotify | other/unclear/4 | catalog/praise/1 | topic,intent,severity |
| `44129679` | Avtar sungh | other/unclear/3 | other/unclear/1 | severity |
| `46842184` | asem, lirik nya kdang gaada kek mana?? | other/unclear/3 | catalog/complaint/2 | topic,intent,severity |
| `5de7f95b` | We are boycotting Swedish app in our protest against Sweden for their desrecpect & descera | other/unclear/2 | other/unclear/1 | severity |
| `aa573851` | I absolutely love Spotify, to me is one of the best Music Apps. Great job Spotify!!! | catalog/praise/1 | other/praise/1 | topic |
| `372d4e67` | Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | other/unclear/3 | usability/request/2 | topic,intent,severity |
| `47f1406d` | Very poor updates as we cannot playback the songs and most bad updates are happening it is | usability/complaint/3 | playback/complaint/4 | topic,severity |
| `82780cbe` | Awesomeness 👌 👏 👍 😍 💖 | usability/praise/1 | other/praise/1 | topic |
| `36609c5c` | Bheekhmangon | other/unclear/3 | other/unclear/1 | severity |
| `f4c8146a` | Unconditional love, Stoli Canales | other/unclear/3 | other/unclear/1 | severity |
| `3ddb3f4e` | Deleting this App. The new update suck, we can't choose our fvrt songs after some clicks,  | usability/complaint/4 | billing/cancellation/3 | topic,intent,severity |
| `16d640e9` | It's my best music app but now it's not...everything basic features is premium.... | usability/complaint/3 | billing/complaint/3 | topic |
| `8cc4fad4` | I hate this app and sweden .I love islam | other/unclear/2 | other/complaint/2 | intent |
| `215463ae` | What is happening with Spotify?? Recently I'm trying to play a song but it doesn't working | usability/complaint/4 | access/complaint/4 | topic |
| `46c0b49f` | Are you out of your mind? This is dangerous! Listening to music in a normal volume and sud | usability/complaint/2 | usability/complaint/3 | severity |
| `283b5843` | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like | other/unclear/3 | billing/request/1 | topic,intent,severity |
| `1d15724a` | Good | usability/praise/1 | other/praise/1 | topic |
| `89ea724c` | Good app! | usability/praise/1 | other/praise/1 | topic |
| `8c0546b0` | 1-Lyrics not getting loaded, 2-can't go back to or start song where to wanted. Pathetic up | usability/complaint/2 | catalog/complaint/3 | topic,severity |
| `b58dd6f0` | The only thing Spotify lacks is the ability to organize saved 
albums/artists into collect | usability/request/3 | usability/request/1 | severity |
| `1a41c7e1` | Worst application 👎👎👎 | usability/complaint/2 | other/complaint/2 | topic |
| `dceb14e7` | I gave one star because I can't give any less than that. the new update is sooooooo annoyi | usability/complaint/2 | usability/complaint/3 | severity |
| `5fba12ea` | I find Spotify very good, it finds and play whatever music you want and also adds songs th | usability/praise/1 | catalog/praise/1 | topic |
| `ac4e860a` | paying for subscribing but unable to play in offline mode really? | usability/complaint/3 | downloads/complaint/4 | topic,severity |
| `9034d675` | Worst app ever too much ad | usability/complaint/3 | usability/complaint/2 | severity |
| `d2f3874f` | Too expensive and the free version is pretty much unusable with constant ads... Every two  | usability/complaint/2 | usability/complaint/3 | severity |
| `ca63dfbe` | I'm loving the experience with the app | usability/praise/1 | other/praise/1 | topic |
| `083811c7` | best app ever | usability/praise/1 | other/praise/1 | topic |

## Notes

These are the **submitted full-run predictions** (`runs/full`, the labels the instructor grades) for the 50 golden reviews, scored
against the same unchanged human labels. The main error analysis is in [../golden_report.md](../golden_report.md), which scores a
separate 50-review run (`runs/golden50`) with the same label_config. Its categories (convention differences, ambiguous boundaries,
likely model errors) apply here too.

**Run-to-run variability.** 9 of the 50 golden reviews received different labels in the two runs despite identical model, prompt,
schema and settings:

| review (start) | golden50 run | full run |
|---|---|---|
| "Staff must be full of mentally ill kool-aid heads…" | other / cancellation / 1 | catalog / complaint / 3 |
| "Update: I reached out to Spotify Support…" | playback / complaint / 4 | playback / complaint / 3 |
| "asem, lirik nya kdang gaada kek mana??" | catalog / request / 1 | catalog / complaint / 2 |
| "We are boycotting Swedish app…" | other / cancellation / 1 | other / unclear / 1 |
| "Unconditional love, Stoli Canales" | other / praise / 1 | other / unclear / 1 |
| "I hate this app and sweden .I love islam" | other / unclear / 2 | other / complaint / 2 |
| "What is happening with Spotify?? Recently I'm trying to play…" | playback / complaint / 4 | access / complaint / 4 |
| "Beth, we all got to give me a free dollar…" | other / unclear / 1 | billing / request / 1 |
| "Too expensive and the free version is pretty much unusable…" | billing / cancellation / 3 | usability / complaint / 3 |

Every case is short, political, non-English or mixed-issue text near a rubric boundary. Clear single-issue reviews were stable. The
model is not deterministic even with thinking disabled. This is why the pipeline caches results by exact text and configuration
(identical inputs are never re-labeled with a different answer within a run), and why borderline cases should be read as uncertain.
The overall agreement is almost unchanged (topic 0.50 → 0.48, intent 0.82 → 0.84, severity 0.60 → 0.62, severity MAE 0.60 → 0.52).
