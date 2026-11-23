# World Brief

A private international news briefing. A Python backend on the desktop collects
reporting from feeds, has a local model (LM Studio) draft source-grounded
summaries, checks every statement against the passages it cites, and serves the
result to a native Android app that caches it for offline reading and listening.

**Read [`docs/STATUS.md`](docs/STATUS.md) first.** It says what has been run and
what has only been written.

```
feeds -> ingest -> dedupe -> cluster -> rank -> summarize -> validate -> publish
                                         |          |            |          |
                                      LM Studio  LM Studio   LM Studio   SQLite -> FastAPI -> Android (Room cache, TTS)
```

## Layout

| Path | What it is |
|---|---|
| `contract/` | The briefing JSON schema (v1), example briefings, fixture generator. Both sides are built against this. |
| `backend/` | Python package `worldbrief`: pipeline, SQLite storage, FastAPI, command line. |
| `android/` | Kotlin + Jetpack Compose app. |
| `docs/` | Architecture, decisions, status, review notes. |
| `.github/workflows/ci.yml` | Runs backend tests and builds the Android debug APK. |

## Backend quick start (Windows PowerShell)

Needs Python 3.11 or newer.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q                      # 13 tests, no network or model needed

copy config.example.toml config.toml     # then set lmstudio.chat_model
python -m worldbrief check-lm            # confirms LM Studio's server answers, lists models
python -m worldbrief run                 # fetch feeds, publish today's briefing
python -m worldbrief status              # last run: log, and every claim that was removed

$env:WORLDBRIEF_API_TOKEN = python -m worldbrief token
python -m worldbrief serve               # http://127.0.0.1:8000
```

To try everything without LM Studio:

```powershell
python -m worldbrief run --stand-in      # rule-based stand-in, for plumbing tests only
python -m worldbrief load-demo ..\contract\examples\briefing-2026-11-23.json
```

In LM Studio: load a model, start the local server (Developer tab), and copy the
model identifier into `config.toml`. Context length and GPU offload are set in
LM Studio's model settings; the backend limits prompt size, output length,
call count, pauses and total run time (see `[lmstudio]` and `[limits]`).

## Connecting the phone

1. Start the API with `python -m worldbrief serve --host 0.0.0.0` (same Wi-Fi) and allow it through Windows Firewall for private networks.
2. In the app: Settings -> World Brief server. Address `http://<desktop-ip>:8000`, token = the value of `WORLDBRIEF_API_TOKEN`.
3. "Save and sync". Downloaded briefings stay on the phone when the desktop is off.

Android emulator on the same PC: use `http://10.0.2.2:8000`.

Plain `http` works in debug builds only. Access from outside the home network
is deliberately not set up yet; see `docs/ARCHITECTURE.md`.

## Android build

Open `android/` in Android Studio (a version that supports Android Gradle
plugin 9.5) and run, or from a terminal: `gradlew.bat assembleDebug`.
Without Android Studio: push this repository to GitHub; the CI workflow builds
the APK and attaches it to the run as `worldbrief-debug-apk`.

## API

| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/v1/health` | none | status and versions |
| GET | `/v1/briefings` | bearer | `{ "briefings": [ {id, date, generatedAt, title, storyCount, isDemo} ] }` |
| GET | `/v1/briefings/latest` | bearer | a briefing (contract v1) |
| GET | `/v1/briefings/{YYYY-MM-DD}` | bearer | a briefing (contract v1) |
