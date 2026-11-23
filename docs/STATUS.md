# Status

Last updated 2026-11-23. Three levels are used and kept apart:

- **Verified**: run, with the result observed.
- **Implemented**: written, not yet run in a way that proves it.
- **Planned**: not written.

## Verified

| What | How it was checked |
|---|---|
| Contract schema and both example briefings | Validated with `jsonschema` (Draft 2020-12). |
| Backend pipeline end to end on fixture feeds | `pytest`, 13 tests passing on Python 3.13. Local RSS files, rule-based stand-in instead of a model. |
| Safeguards: fabricated passage reference removed, unsupported claim removed, wrong figure flagged, contradicted claim removed, checker outage downgrades claims | `pytest`, scripted misbehaving model. |
| One failing feed, one failing event, and the time limit do not lose the run | `pytest`. |
| LM Studio client request shape, JSON retry, prompt cap, call budget | `pytest` against a mock HTTP server. **Not** against a real LM Studio. |
| API: token required, list, by date, latest, 404 | `pytest` and a live `uvicorn` run queried with `curl`. |
| Command line: `run --stand-in`, `load-demo`, `serve`, `status`, `token` | Run by hand on Linux. |
| Android narration script and date formatting (pure Kotlin) | Compiled with Kotlin 2.0.21 and its three unit tests run with a minimal test runner. |
| Every Android Kotlin file parses | Kotlin 2.0.21 compiler found no syntax errors. This does not check types or library calls. |
| Icon drawables | Rendered and looked at. |

## Implemented, not verified

| What | Why not verified | How to verify |
|---|---|---|
| **The Android app as a whole** | The environment it was written in cannot download Android libraries, so no Gradle build has run. Expect some compile errors on the first build. | Android Studio, or push to GitHub and read the `Android build` job. |
| **Android toolchain versions** (AGP 9.5.1, Gradle 9.6.0, Kotlin 2.4.21, KSP 2.3.13, Compose BOM 2026.11.01, compileSdk 37.1) | Read from official release pages; the combination is untested. | Same build. |
| Real LM Studio inference | No LM Studio in the build environment. | `worldbrief check-lm`, then `worldbrief run`. |
| Real feeds | The feed URLs in `config.example.toml` could not be reached from the build environment. | `worldbrief run`, then `worldbrief status`. |
| Embedding-based clustering | Needs an embedding model in LM Studio. Word-overlap clustering is what the tests exercise. | Set `lmstudio.embedding_model`. |
| Windows | Backend was run on Linux only. Nothing in it is OS-specific, but it has not run on Windows. | Run the quick start. |
| App behaviour on a phone: Room, sync, text-to-speech, theme, navigation | Needs a build. | Install the debug APK. |

## Planned

- Model benchmark command: latency, memory, removed-claim rate per model, on a fixed article set.
- Scheduled daily run (Windows Task Scheduler) and a start-on-boot API.
- Background sync and new-briefing notification on Android (WorkManager).
- Foreground playback service with lock-screen controls and audio focus.
- Remote access (Tailscale or similar) with HTTPS; encrypted token storage on the phone.
- Reuse of the existing multi-agent project's LM Studio code, once that project is located.
- Full-text retrieval where an outlet's terms allow it.
- Search using SQLite full-text index; archive pruning.

## Known limitations of what exists

- Summaries can only be as detailed as the excerpts in the feeds, which are often one or two sentences.
- The checks establish that a statement matches its cited sources. They cannot establish that the sources are correct.
- Names and figures are matched as text. "Three" in a source and "3" in a claim is flagged as a mismatch (the claim is marked partly confirmed, not removed).
- Wire-copy detection is a pattern match on agency credits and near-identical text. Rewritten wire copy counts as an independent source.
- Pausing narration restarts the current story when resumed; Android's speech engine cannot pause mid-sentence.
- The app stores the access token unencrypted in its private storage.
