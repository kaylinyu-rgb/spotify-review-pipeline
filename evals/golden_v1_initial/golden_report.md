# Golden-set evaluation (50 human labels vs saved predictions)

Run `golden50`, label_config `anthropic:claude-haiku-5-5+effort-low+enrich-p2+schema-s2+entities-l1`. Valid predictions 50/50; ambiguous (human-marked) 0.

| metric | value |
|---|---|
| topic_accepting_alternatives agreement | 0.5 |
| topic_exact agreement | 0.5 |
| intent agreement | 0.82 |
| severity_exact agreement | 0.6 |
| sentiment_within_0.5 agreement | 0.98 |
| all_three agreement | 0.28 |
| needs_review_match agreement | 0.9 |
| severity MAE | 0.6 |
| sentiment MAE | 0.11 |
| evidence quote exact-substring rate | 1.0 |
| topic macro-F1 | 0.353 |
| intent macro-F1 | 0.709 |

## Topic confusion (human → predicted)

| human | predicted | n |
|---|---|---|
| catalog | catalog | 1 |
| catalog | other | 1 |
| other | billing | 1 |
| other | catalog | 2 |
| other | other | 16 |
| other | usability | 1 |
| support | playback | 1 |
| usability | billing | 3 |
| usability | catalog | 2 |
| usability | downloads | 1 |
| usability | other | 10 |
| usability | playback | 3 |
| usability | usability | 8 |

## Disagreements (36)

| review_id | text | human t/i/s | model t/i/s | fields |
|---|---|---|---|---|
| `292ce26a` | Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks  | other/unclear/4 | other/cancellation/1 | intent,severity |
| `a70e8d3e` | Great app use it every chance I get | usability/praise/1 | other/praise/1 | topic |
| `0d4f8b48` | It's really an amazing experience with Spotify...I love it🥰 | usability/praise/1 | other/praise/1 | topic |
| `599a0d41` | I just loved it | usability/praise/1 | other/praise/1 | topic |
| `1fc8b08f` | Duo Premium .... No ads at all! | other/praise/1 | billing/praise/1 | topic |
| `947821dc` | Very good but wen I play my song it o ly plays a little bit then it stops I updated my pho | usability/complaint/3 | playback/complaint/3 | topic |
| `723f07de` | Update: I reached out to Spotify Support and with some help from Sarah I was able to get t | support/request/3 | playback/complaint/4 | topic,intent,severity |
| `47428620` | This app is bad work | usability/complaint/2 | other/complaint/2 | topic |
| `01d453b0` | I like it but god I hate it when the music Interrupts my ads | usability/complaint/3 | usability/complaint/2 | severity |
| `ac6cd66d` | Lhat ng song nasa spotify | other/unclear/4 | catalog/praise/1 | topic,intent,severity |
| `44129679` | Avtar sungh | other/unclear/3 | other/unclear/1 | severity |
| `46842184` | asem, lirik nya kdang gaada kek mana?? | other/unclear/3 | catalog/request/1 | topic,intent,severity |
| `5de7f95b` | We are boycotting Swedish app in our protest against Sweden for their desrecpect & descera | other/unclear/2 | other/cancellation/1 | intent,severity |
| `aa573851` | I absolutely love Spotify, to me is one of the best Music Apps. Great job Spotify!!! | catalog/praise/1 | other/praise/1 | topic |
| `372d4e67` | Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | other/unclear/3 | usability/request/2 | topic,intent,severity |
| `47f1406d` | Very poor updates as we cannot playback the songs and most bad updates are happening it is | usability/complaint/3 | playback/complaint/4 | topic,severity |
| `82780cbe` | Awesomeness 👌 👏 👍 😍 💖 | usability/praise/1 | other/praise/1 | topic |
| `36609c5c` | Bheekhmangon | other/unclear/3 | other/unclear/1 | severity |
| `f4c8146a` | Unconditional love, Stoli Canales | other/unclear/3 | other/praise/1 | intent,severity |
| `3ddb3f4e` | Deleting this App. The new update suck, we can't choose our fvrt songs after some clicks,  | usability/complaint/4 | billing/cancellation/3 | topic,intent,severity |
| `16d640e9` | It's my best music app but now it's not...everything basic features is premium.... | usability/complaint/3 | billing/complaint/3 | topic |
| `215463ae` | What is happening with Spotify?? Recently I'm trying to play a song but it doesn't working | usability/complaint/4 | playback/complaint/4 | topic |
| `46c0b49f` | Are you out of your mind? This is dangerous! Listening to music in a normal volume and sud | usability/complaint/2 | usability/complaint/3 | severity |
| `283b5843` | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like | other/unclear/3 | other/unclear/1 | severity |
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
| `d2f3874f` | Too expensive and the free version is pretty much unusable with constant ads... Every two  | usability/complaint/2 | billing/cancellation/3 | topic,intent,severity |
| `ca63dfbe` | I'm loving the experience with the app | usability/praise/1 | other/praise/1 | topic |
| `083811c7` | best app ever | usability/praise/1 | other/praise/1 | topic |

## Error analysis (write by hand after reading the table)

_TODO: group the disagreements by cause (rubric ambiguity, model error, human error, non-English text) and say what you changed or why you did not._
