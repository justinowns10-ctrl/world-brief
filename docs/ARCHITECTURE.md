# Architecture

## Shape

Two programs and one contract.

- **Backend** (desktop, Python): turns feeds into one briefing per day and serves briefings over HTTP.
- **App** (Android, Kotlin): downloads briefings, stores them, shows and reads them aloud.
- **Contract** (`contract/briefing.schema.json`): the only thing the two share. It says nothing about feeds, models or LM Studio, so either side can be replaced.

The app never talks to LM Studio. LM Studio listens on localhost and only the backend calls it.

## The contract (schema version 1)

A briefing has `sources`, `stories` and `publication` (state, reasons, event counts). A story has:

| Field | Meaning |
|---|---|
| `section` | One of six regions, `other_regions`, or five topics. |
| `status` | `verified`, `preliminary` or `disputed` (rules below). |
| `eventDate` | The day the event happened, only if a source states it. Otherwise null. |
| `firstReportedAt`, `articles[].publishedAt` | Reporting dates. Kept separate from the event date. |
| `claims[]` | The factual statements, in order. Each has `support` (`supported`, `partial` or `unchecked`), an optional `note`, and `evidence[]`: an article id plus a passage from that article. |
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

Word overlap is used only to find the source sentence a statement corresponds to. Finding it proves nothing: "A invaded B" and "B invaded A" overlap completely. Separate rules then accept, flag or remove.

For every drafted claim, in order:

1. **Provenance.** It must cite at least one passage that was shown to the model. Links are resolved from stored records by id, so a fabricated URL cannot reach a briefing.
2. **Retrieval.** A sentence matching the claim or its quote must be found in a cited article. The published quote is that source sentence, not the model's wording.
3. **Removal rules.** The claim is removed if the source sentence negates it, if the claim adds a negation, if it swaps a term for its opposite, or if shared names appear in a different order.
4. **Downgrade rules.** The claim becomes `partial` if the source hedges it, if it asserts a cause the source does not, if a figure or name is absent from the cited passages, or if another passage gives a different figure for the same point (which also marks the story as in conflict).
5. **Model check.** A second call, given only the cited passages and the statements, returns `supported`, `partial`, `unsupported` or `contradicted` per statement, and says whether the passages disagree.
6. **Outcome.** The worst result wins. `unsupported` and `contradicted` claims are removed and recorded in `claim_audit` with the reason.
7. **No verdict.** If the model check did not run or skipped a claim, the claim is published only if it is one whole source sentence word for word, labelled `unchecked`. Paraphrases are removed.

Other fields:

- **Headline**: used only if every content word comes from the sources and it passes the removal rules; otherwise the lead outlet's own headline.
- **Background**: must match a source sentence, pass the claim rules, and be approved by the model check.
- **Why it matters**: no figure, name or causal word absent from the sources, and explicit approval from the model check. Never published unchecked.
- **Event date**: kept only if a passage states it (day and month, a weekday within the prior week, "today", "yesterday"). Otherwise null.

Story status:

- `disputed`: the sources conflict, or a claim was contradicted.
- `verified`: two or more independent sources, every published claim `supported`, and the model check ran.
- `preliminary`: everything else.

### Editorial rules that do not depend on the model

- **What kind of article it is** (`ingest.article_kind`): news, opinion, analysis, live or sport, from the address and headline. Only news is a source of claims. Analysis may be grouped with its event as related reading.
- **Where it happened** (`geo.py`): countries are found by place names and nationalities; the section is the region with the most mentions, headlines counting triple. The United States yields to another region with at least half its score, since it is often an actor in a story set elsewhere.
- **Region or topic**: the model proposes; a topic section is accepted only if the headlines use that topic's vocabulary, or if the event spans regions and most headlines describe it in that topic's terms.
- **United States only**: capped at importance 2.
- **What kind of claim it is** (`validate.claim_nature`): event, statement or forecast, from its wording.

### Untrusted article text

Feed text is treated as hostile input. Sentences that read as instructions to a model are removed before a passage is shown to the model, and an article whose headline is such an instruction is withheld entirely. Both prompts tell the model that passages are material to report on, not instructions. Whatever the model writes still has to pass validation against the cleaned passages.

### Publication states

| State | Meaning | Where it appears |
|---|---|---|
| `pending` | A run is in progress, or none has started. | `GET /v1/status`, `worldbrief status` |
| `complete` | Published, nothing cut short. | briefing `publication.state`, briefing list, status |
| `partial` | Published, but a feed could not be read, a story was lost to an error, verification could not finish for a story, or the budget or time limit stopped the run. `publication.reasons` says which; `publication.events` gives the counts. | same |
| `failed` | Nothing published. An earlier briefing for that date is left in place. | status only: there is no briefing to carry it |

A run found still marked as running when the next one starts was interrupted and is recorded as failed.

### Story identity

A story's id is the briefing date plus the id of the earliest report of that event. Regenerating a briefing keeps the id even if the order or the set of articles changes, so saved stories on the phone keep pointing at the same event.

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
