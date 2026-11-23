# Status

Last updated 2026-11-23, after the first successful Android build and the editorial-correctness round.
Git: `baseline-0.1` is the code as first delivered; this work is on branch `directive-01`.

Three levels are used and kept apart:

- **Verified**: run, with the result observed. Evidence is in `reports/`.
- **Implemented**: written, not yet run in a way that proves it.
- **Planned**: not written.

## Android: first successful build (2026-11-23)

GitHub Actions, run on the first push, with no source changes needed:

- `compileDebugKotlin`, `kspDebugKotlin` (Room), `testDebugUnitTest` and `assembleDebug` all passed. **BUILD SUCCESSFUL in 2m 14s.**
- One compiler warning: a deprecated text-field API in the settings screen.
- Toolchain as pinned: AGP 9.5.1, Gradle 9.6.0, Kotlin 2.4.21, KSP 2.3.13, Compose BOM 2026.11.01, compileSdk 37.1.
- Full job log: `reports/android-ci/2026-11-23-first-successful-build.log`. The APK is the `worldbrief-debug-apk` artifact on that run (14.3 MB).

What this does and does not establish: the app compiles, its unit tests pass, and an installable debug APK exists. **Nobody has installed or opened it.** Screens, Room at runtime, sync against the real server, and text-to-speech are still untested.

## Editorial-correctness round (after the first real briefing)

Driven by what the first real briefing got wrong (listed below) and by a claim-by-claim review (`benchmarks/2026-11-23-first-real-run/REVIEW-SUMMARY.md`): of 21 claims published as supported, 16 were correct, 3 dropped an attribution and 2 came from an opinion column.

| Problem observed | Change | Checked how |
|---|---|---|
| Wrong sections | Region is looked up from place names (`geo.py`, about 190 countries with cities and nationalities). The model only chooses region versus topic, and a topic needs support in the headlines. Countries come from the reports, not the model. | Re-run of the rules over the first run's articles: all twelve stories land where a reader would expect. Tests in `test_editorial.py`. |
| Opinion as fact | Articles are sorted by address and headline into news, opinion, analysis, live and sport. Only news is a source of claims. | On the first run's 97 articles: 75 news, 10 analysis, 6 sport, 4 live, 2 opinion. Both opinion columns are excluded. |
| Dropped attribution, unattributed judgement, forecasts | Claims are marked partly confirmed when the source attributes and the claim does not, or when a judgement word has no owner. Each claim carries `nature`: event, statement or forecast. | Tests. |
| One event split into several stories | Clustering now weights names, acronyms and countries, uses average-link grouping, and joins reports naming the same coded event (COP31, G20). | On the first run's articles: 85 usable articles form 52 events, 12 of them with two or more independent sources, against 3 before. The largest story of the day, missed entirely by the first briefing, is now one seven-report event. |
| United States domestic story at importance 4 | A story set only in the United States is capped at importance 2. | Test. |
| True claims removed; harmless wording flagged | Name-order rule narrowed to real role swaps; alternative country names accepted; qualifiers read only from the part of the sentence the claim uses; long run-on passages cut into windows. | Tests reproducing each case. |

Backend suite: **81 tests pass.**

**Not yet verified:** these changes have not been through a second real run. The clustering and section results above come from re-running the deterministic stages on the first run's stored articles, which is real data but the same day the rules were tuned on. Whether the claim rules behave on fresh model output is unknown.

Known weak points of the new rules: the article sorter is conservative (a news report with a question for a headline is treated as analysis, and feature sections are excluded wholesale); the place table has no people and few cities; topic vocabulary is a short word list; "may" the month still reads as a hedge.

## First run on the Windows desktop (2026-11-23, 05:35 local)

`run_verify.bat` was run on the desktop. Test and build output is in `reports/windows-2026-11-23/`; the real run is in `benchmarks/2026-11-23-first-real-run/`.

| Step | Result | Evidence |
|---|---|---|
| Python found, packages installed | OK. Python 3.14.10 from Miniforge. | `windows-summary.txt`, `windows-pip.txt` |
| Backend test suite on Windows | **60 passed** | `windows-pytest.txt` |
| Six starter feeds, live | **All six OK**: 170 entries, every one usable. | `benchmarks/.../feeds.json` |
| LM Studio reachable | OK. LM Studio 0.4.28. | `benchmarks/.../lmstudio-models.txt` |
| Real run, real feeds, real model | **Published, state `complete`**: 12 stories from 97 articles. | `benchmarks/2026-11-23-first-real-run/MEASUREMENTS.md` |
| Android build on the desktop | **Failed before starting**: no Java on the machine. Android Studio and the Android SDK are not installed either. The build was done on GitHub instead (above). | `reports/windows-2026-11-23/android-build.log` |

Real-run measurements:

- Model `openai/gpt-oss-20b`, quantization MXFP4 (4 bits per weight), GGUF, 12.1 GB. Loaded with context 8192, 4 parallel slots, flash attention on. The backend sent one request at a time, output capped at 2000 tokens.
- 26 model calls, 90.0 s of inference, 117.2 s wall time. Ranking 12.0 s per call, drafting 2.3 s, checking 3.2 s. About 120 output tokens per second.
- Peak GPU memory 13,591 of 16,303 MiB (13,504 before the run, so the model was already loaded), GPU load peak 63 %, 60 C. System memory peak 33.7 of 97.7 GB. Whole-machine figures.
- Validation: 29 claims drafted, 21 supported, 5 partly confirmed, 3 removed. Stories: 2 verified, 9 preliminary, 1 disputed.

Not yet exercised on Windows: the API server (`worldbrief serve`) and anything on a phone.

### What the real briefing got wrong

Found by reading it. The briefing itself is in `benchmarks/2026-11-23-first-real-run/` on the desktop; it is not in Git.

1. **Sections were often wrong.** Stories about the Middle East and Southeast Asia were filed under "other regions", and a story about diplomatic talks under "energy". The coverage note then wrongly said those regions had no stories.
2. **Opinion was published as fact.** A sweeping judgement from an opinion column went out as a supported claim. It matched its source; nothing separated commentary from reporting.
3. **Clustering was weak.** 97 articles became 74 events; two reports of one summit became two stories. Nine of twelve stories rested on one source.
4. **A United States domestic story was selected** at importance 4.
5. **No story had an event date.**
6. **The rules over-removed.** Two of the three removals were true claims removed by the name-order rule. The third is debatable. (An earlier version of this note said the model had invented that claim. It had not: the outlet did report the figure.)
7. **"Why it matters" survived for only 3 of 12 stories.**

## Verified

| What | Evidence |
|---|---|
| Backend test suite: 60 tests pass on Linux, Python 3.13 | `reports/backend-pytest-linux.txt` |
| Contract schema; both example briefings validate | test `test_example_briefings_are_valid` |
| Publication states: complete, partial, failed, pending, in the briefing, the list, the run record and `GET /v1/status` | `tests/test_states.py` |
| Model-call budget exhaustion: mid-run (partial), between draft and check (unchecked claims, partial), before any story (failed), zero budget (failed), and that no request is sent past the budget | `tests/test_states.py`, real client code against a fake LM Studio server |
| A failed run leaves the earlier briefing for that date in place; an interrupted run is recorded as failed | `tests/test_states.py` |
| Story ids survive regeneration in a different order (WB-004) | `test_story_ids_survive_regeneration_in_a_different_order` |
| Adversarial verification: wrong weekday, wrong day, unsupported event date, conflicting figures, figure from an uncited passage, denial, negation, added negation, hedge dropped, attribution dropped, reversed term, swapped roles, unstated cause, quote from the wrong article, sentence fragment | `tests/test_adversarial.py` |
| Verifier unavailable: only word-for-word source sentences are published, labelled `unchecked`; paraphrases, analysis and background are not (WB-001) | `test_unavailable_verifier_publishes_only_word_for_word_claims` and two others |
| Headline, background and analysis cannot add a figure, name, cause or reversal; analysis needs an explicit model approval (WB-002) | `tests/test_adversarial.py`, narrative section |
| Instructions planted in an article never reach the model; a model that "obeys" anyway has its claim, headline, analysis and date removed | `test_planted_instruction_never_reaches_the_model_and_its_claim_is_removed` |
| Feeds: HTTP 404, HTTP 500, timeout, connection refused, HTML page, empty body, binary garbage, truncated XML (partly recovered), undated entries, Atom | `tests/test_feeds.py`, real local HTTP server |
| `run --report` writes its JSON and Markdown report | test, with the stand-in model |
| Android: every Kotlin file parses; narration and date unit tests pass | `reports/android-kotlin-syntax-check.txt`. Parse check only, old compiler. Not a build. |

What these tests are not: no test used a real language model or a real news feed. They show the pipeline's rules behave as written. They say nothing about how good a real model's drafts are or how many real claims the rules will wrongly remove.

## Starter feeds against live endpoints

Checked from the build environment with a fetch tool on 2026-11-23:

| Feed | Result |
|---|---|
| Al Jazeera | Valid RSS 2.0, 25 items, each with link, title, description and date; newest item under an hour old. |
| BBC, Deutsche Welle, The Guardian | Could not be checked: the fetch tool blocks these sites. Says nothing about whether they work from the desktop. |
| France 24 | Could not be checked: the site's robots rules refuse automated fetching of that address. Worth reading their terms before relying on it. |
| UN News | Request failed with a client error. The address may be wrong or may refuse this tool. |

So one of six is confirmed. `python -m worldbrief check-feeds` on the desktop settles the rest in one command.

## Implemented, not verified

| What | How to verify |
|---|---|
| The Android app at runtime: screens, Room, sync, narration, partial and unchecked labels | Install the APK on a phone or emulator. It compiles and its unit tests pass; nothing more is known. |
| Bookmarks surviving regeneration on the phone | Follows from stable story ids (tested in the backend) and bookmarks being keyed by story id. Needs an on-device check. |
| Embedding-based clustering | Set `lmstudio.embedding_model`. |

## Known limits of the verification rules

- They establish that a published statement matches its cited source. They cannot establish that the source is right.
- **Scope changes in number words** are not caught without the model check: "two of the five ministers resigned" rewritten as "the five ministers resigned". A test pins this.
- Figures and names are compared as text. "Three" against "3" is flagged as a mismatch.
- The rules are conservative and will remove some true claims: a correct passive rewrite trips the name-order rule; "not" anywhere in the matched source sentence removes a claim that lacks it; "may" the month reads as a hedge. Removed claims are listed by `worldbrief status`, so the cost can be measured on real runs.
- The opposite-term list is a fixed list of about forty pairs.
- Instruction detection is pattern-based. A planted instruction phrased in a way the patterns miss reaches the model; the claim checks still apply to whatever the model then writes.
- Analysis ("why it matters") is the weakest field: by nature it is not stated in the sources. It is published only when it adds no figure, name or causal word and the model check explicitly approves it. With a weak checking model, expect it to be mostly absent or occasionally wrong.
- Wire-copy detection is a pattern match; rewritten wire copy counts as an independent source.

## Backlog from review (not started, not blockers for the first APK)

- **WB-008 Persistent event identity.** A story id is the briefing date plus the id of the event's earliest report. It survives reordering, but changes if an earlier article joins the cluster on a later run. Needs a stored event table or a remapping from old ids to new.
- **WB-009 Verification independence.** Drafting and checking may use the same local model, so the second pass is a consistency check, not independent corroboration. During real LM Studio testing, hand-review a sample of claims and count false approvals (published but wrong) and false rejections (removed but right). `claim_audit` and the real-run report list every claim with its verdict, which is the sample frame.

## Planned (unchanged; nothing here was started)

Scheduling, background sync and notifications on Android, foreground playback service, remote access with HTTPS, encrypted token storage, reuse of the existing multi-agent project's LM Studio code, a multi-model benchmark command, the app reading `GET /v1/status`.
