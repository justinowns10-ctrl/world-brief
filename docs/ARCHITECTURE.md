# Architecture

## Shape

Two programs and one contract.

- **Backend** (desktop, Python): turns feeds into one briefing per day and serves briefings over HTTP.
- **App** (Android, Kotlin): downloads briefings, stores them, shows and reads them aloud.
- **Contract** (`contract/briefing.schema.json`): the only thing the two share. It says nothing about feeds, models or LM Studio, so either side can be replaced.

The app never talks to LM Studio. LM Studio listens on localhost and only the backend calls it.

## The contract (schema version 1)

A briefing has `sources` and `stories`. A story has:

| Field | Meaning |
|---|---|
| `section` | One of six regions, `other_regions`, or five topics. |
| `status` | `verified`, `preliminary` or `disputed` (rules below). |
| `eventDate` | The day the event happened, only if a source states it. Otherwise null. |
| `firstReportedAt`, `articles[].publishedAt` | Reporting dates. Kept separate from the event date. |
| `claims[]` | The factual statements, in order. Each has `support` (`supported` or `partial`), an optional `note`, and `evidence[]`: an article id plus a passage from that article. |
| `summary` | The claims joined. There is no factual text outside the claims. |
| `whyItMatters`, `context` | Analysis and background. Labelled as such in the app; not presented as verified fact. |
| `uncertainty` | What is unknown, single-sourced, partly confirmed, removed or in conflict. |
| `independentSourceCount` | Sources after collapsing copies and shared wire reports. |
| `articles[]` | Links to the original reports, each with its outlet, publication time and role (`original`, `wire`, `syndicated`). |

Unknown fields are ignored by the app, so fields can be added without a version bump. A change that removes or redefines a field needs `schemaVersion` 2.

`other_regions` is an addition to the six regions in the project brief. Without it, events in North America, Oceania or Central Asia have nowhere to go and would be mis-filed or dropped.

## Backend pipeline

| Stage | Module | Uses the model? | What it does |
|---|---|---|---|
| Ingest | `ingest.py` | no | Fetches each feed, normalizes entries, strips tracking parameters, stores source records in SQLite. Undated entries are skipped. |
| Dedupe | `ingest.py` | no | Marks same-title and near-identical text as copies; marks wire-credited text. Copies stay as links but do not count as independent sources. |
| Cluster | `cluster.py` | embeddings only, optional | Groups articles about one event by vector similarity. Falls back to word statistics. |
| Rank | `rank.py` | yes, batched | Assigns section, importance and countries. A failed batch is ranked by rule. Selection gives every region with a qualifying event at least one slot, then fills by importance. |
| Summarize | `summarize.py` | yes, one call per story | Drafts claims from numbered passages. The model cites passage labels (A1, A2) and never writes a URL. |
| Validate | `validate.py` | yes, one call per story | See below. |
| Publish | `pipeline.py` | no | Assembles the briefing, validates it against the schema, stores it, writes a JSON copy. |

One model, three prompts. There are no separate "agents": a regional analyst would be the same model under another name. The one second opinion that earns its cost is the checking pass, which sees only the cited passages and the statements.

### Validation

For every drafted claim, in order:

1. **Provenance.** It must cite at least one passage that was actually shown to the model. A reference to anything else removes the claim. Because links are resolved from stored records by id, a fabricated URL cannot reach a briefing.
2. **Passage match.** Text matching the claim or its quote must be found in a cited article. The published quote is taken from the stored source record, not from the model's output.
3. **Figures and names.** Any number or capitalised name in the claim that is absent from the cited passages marks the claim `partial` with a note saying which.
4. **Consistency check.** A second model call, given only the cited passages and the statements, returns `supported`, `partial`, `unsupported` or `contradicted` per statement, and says whether the passages disagree with each other.
5. **Outcome.** The worse of steps 3 and 4 wins. `unsupported` and `contradicted` claims are removed and recorded in the `claim_audit` table with the reason. If the check cannot run, surviving claims are downgraded to `partial`. A story with no surviving claim is dropped.

Story status:

- `disputed`: the sources conflict, or a claim was contradicted.
- `verified`: two or more independent sources, every published claim `supported`, and the consistency check ran.
- `preliminary`: everything else.

Analysis and background text is dropped if it contains a figure that appears in no source.

What this does and does not show: it shows that published statements are what the cited reports say. It does not show the reports are true. The app says so on every story.

### Workload limits

Set in `config.toml`; defaults in brackets.

- Inference is sequential. One request at a time, always.
- Per call: timeout [180 s], prompt cap [14,000 characters], output cap [900 tokens], retries [2], pause after each call [1 s].
- Per run: model calls [80], wall-clock time [45 min], articles [300], candidate events [40], stories [12], passages per story [5], characters per passage [1,500].
- With defaults a run makes at most 2 ranking calls plus 2 calls per story: about 26 calls.
- Model memory (context length, GPU layers) is set in LM Studio, not here. `model_ttl_s` can ask LM Studio to unload the model after the run.

### Failure handling

- A feed that fails is logged and skipped.
- A story whose draft or check fails is logged and skipped.
- When the call budget or time limit is reached, the stories already finished are published and the briefing's coverage notes say it is short.
- Re-running for the same date replaces that date's briefing.
- Every run writes to `runs` and `run_events`; `worldbrief status` prints the last run and the claims it removed.

### Storage

SQLite, one file: `sources`, `articles` (source records), `runs`, `run_events`, `claim_audit`, `briefings` (the published JSON).

### API and network

FastAPI, read-only, one bearer token from the `WORLDBRIEF_API_TOKEN` environment variable. Host and port are configuration: `127.0.0.1` by default, `0.0.0.0` for home-network testing. Nothing about remote access is built in, so Tailscale or another route can be chosen later without code changes. On the app side the server address is a setting.

## Android app

Single module, package `com.worldbrief.app`.

```
data/model      domain types (Briefing, Story, Claim, Section ...)
data/remote     contract DTOs, BriefingSource (bundled demo data | HTTP server)
data/local      Room entities, DAO, database
data/           mappers and validation, BriefingRepository, SettingsRepository
tts/            NarrationScript (pure), Narrator (Android TextToSpeech)
ui/             theme, components, navigation, one package per screen
```

- **Data flow.** Screens read only from Room, through the repository, as Flows. `refresh()` copies new or changed briefings from the configured source into Room. If the server is unreachable the stored briefings are untouched, which is how offline reading works.
- **Navigation.** Bottom bar: Today, Archive, Saved, Settings. Routes: `briefing/{id}`, `section/{briefingId}/{sectionKey}`, `story/{storyId}`.
- **State.** One ViewModel per screen, exposing a StateFlow. Dependencies come from a small hand-written container.
- **Narration.** One segment per story so playback can pause, resume and skip. Status and uncertainty are spoken, since a listener cannot see labels.

### Decisions that differ from the original brief

| Decision | Reason |
|---|---|
| No Retrofit or Ktor yet; `HttpURLConnection` | Three GET requests. A library can replace `HttpBriefingSource` without touching anything else. |
| No Hilt | Five objects to wire. |
| Room 2.8, Navigation 2.10 | Current stable lines with long-established APIs. Room 3 and Navigation 3 exist; moving is a later, isolated change. |
| Vector drawables instead of the Material icons library | Fewer dependencies, and only the sixteen icons used are shipped. |
| WorkManager not added yet | Background sync and notifications are the next milestone; nothing uses it today. |
| Demo data kept | It is the contract's example file, used as a test fixture and as first-run content. It is removed from the phone once a server sync succeeds. |

## Risks

1. **First Android build.** Versions are current but the combination is untested. Likely trouble spots: the `compileSdk` 37.1 block, KSP with built-in Kotlin, API changes in Compose 1.13 and Material 3 1.5.
2. **Model quality on 16 GB of VRAM.** Unknown until measured. The pipeline is built to lose claims, not publish bad ones, so a weak model shows up as short briefings and many removed claims in `worldbrief status`.
3. **Feed terms and stability.** Outlets change or restrict feeds. Each feed is isolated; check terms before adding one.
4. **Thin source text.** Feed excerpts limit depth and make the figure and name checks strict.
5. **Phone to desktop reachability.** Firewall, sleep, changing IP address. Remote access is a later decision.

## Next milestone

1. Get the Android build green (Android Studio or CI) and installed on the phone.
2. Run the backend on the desktop with one real model and the starter feeds; read `worldbrief status`.
3. Connect the phone over home Wi-Fi.
4. Then: model benchmark, scheduling, notifications.
