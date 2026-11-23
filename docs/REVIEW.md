# Notes for independent review

What to look at, in order of how much a mistake would cost.

1. **`backend/src/worldbrief/validate.py`** and its tests in `backend/tests/test_backend.py`.
   Is there a path by which a statement the sources do not support reaches a briefing?
   Known gaps are listed under "Known limitations" in `STATUS.md`.
2. **`contract/briefing.schema.json`**. Is anything the app needs missing? Is anything tied to a particular news provider or model?
3. **`backend/src/worldbrief/pipeline.py`**: the status rules (`verified` / `preliminary` / `disputed`) and failure handling.
4. **`backend/src/worldbrief/rank.py`**: the selection rule that reserves a slot per region. Does it balance coverage without inventing importance?
5. **`backend/src/worldbrief/lm.py`**: the workload limits.
6. **`android/`**: not yet compiled. Review is most useful after the first build log exists.

Test results to request: output of `python -m pytest -q` in `backend/`, and the `Android build` job log from CI.

Decisions already taken and why are in `ARCHITECTURE.md`, including where the implementation departs from the original brief.
