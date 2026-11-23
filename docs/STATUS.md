# Status

Last updated 2026-11-23, after Technical Review Directive 01 and ChatGPT's review (WB-001 to WB-007).
Git: `baseline-0.1` is the code as first delivered; this work is on branch `directive-01`.

Three levels are used and kept apart:

- **Verified**: run, with the result observed. Evidence is in `reports/`.
- **Implemented**: written, not yet run in a way that proves it.
- **Planned**: not written.

## Not done: the three results the directive asked for first

| Required result | State | Why | What produces it |
|---|---|---|---|
| Android Gradle build result and log | **Not obtained** | The environment this was written in cannot download Android libraries, has no GitHub repository attached, and was refused access to the desktop's folders. | `scripts\verify_windows.ps1` on the desktop, or push to GitHub (CI keeps the full log as `android-build-log`). |
| Real LM Studio model test | **Not obtained** | LM Studio runs on the desktop only. | `python -m worldbrief run --report ..\reports\real-run.json` (the script does this). The report records model id, quantization, load settings, per-call timings, tokens, peak GPU and system memory, and every removed claim. |
| Windows execution | **Not obtained** | Same. | The script, or the `windows-latest` CI job for the test suite. |

The Android client is **not complete** and must not be described as such until an APK builds.

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
| The Android app as a whole, and its toolchain versions | A Gradle build. |
| Android handling of `partial` briefings and `unchecked` claims (DTO, Room columns, screens) | A Gradle build; `DemoDataTest` covers the mapping. |
| Bookmarks surviving regeneration on the phone | Follows from stable story ids (tested in the backend) and bookmarks being keyed by story id. Needs an on-device check. |
| Real LM Studio inference; LM Studio model-info lookup (tries `/api/v1/models`, then `/api/v0/models`) | The real-run report. |
| GPU and memory sampling (`nvidia-smi`, `psutil`) | The real-run report. Neither tool exists in the build environment, so only the "not available" path has run. |
| `scripts\verify_windows.ps1` | Has never been run. Each step is also listed as a plain command in the README. |
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

## Planned (unchanged; nothing here was started)

Scheduling, background sync and notifications on Android, foreground playback service, remote access with HTTPS, encrypted token storage, reuse of the existing multi-agent project's LM Studio code, a multi-model benchmark command, the app reading `GET /v1/status`.
