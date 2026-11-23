# Review record

## Response to ChatGPT's review of 2026-11-23 (WB-001 to WB-007)

| Item | Outcome | Where | Tests |
|---|---|---|---|
| **WB-001** Verification fallback | **Changed.** When the checking model gives no verdict, a claim is published only if it is one whole source sentence, word for word; it is labelled `unchecked` and the story carries a "VERIFICATION INCOMPLETE" note. Paraphrases are removed. Claim support is now `supported`, `partial` or `unchecked`. | `validate.py` (`is_verbatim`, end of `validate_event`), `pipeline.py` (`build_story`) | `test_unavailable_verifier_publishes_only_word_for_word_claims`, `test_checker_that_skips_a_claim_does_not_let_a_paraphrase_through`, `test_added_negation_and_sentence_fragments`, `test_budget_runs_out_between_draft_and_check` |
| **WB-002** Narrative fields | **Changed.** Headline: every content word must come from the sources, with no dropped negation, flipped term or reordered names; otherwise the lead outlet's own headline is used. Background: must match a source sentence and pass the claim rules, then needs the model check. Analysis: no new figure, name or causal word, and an explicit `supported` from the model check; never published unchecked. | `validate.py` (`safe_headline`, `safe_text`, narrative block) | `test_unsupported_causal_interpretation_is_not_published`, `test_background_must_be_stated_by_a_source`, `test_headline_cannot_flip_or_extend_the_sources`, `test_headline_and_analysis_cannot_add_facts_the_sources_lack` |
| **WB-003** Publication completeness | **Changed, with one difference from the suggestion.** A briefing carries `publication.state` (`complete` or `partial`), `reasons`, and `events` (selected, processed, published, skippedUnsupported, skippedErrors, unprocessed). `failed` is not a briefing value: a failed run publishes nothing, so there is no briefing to carry it. `failed` and `pending` are reported per run by `GET /v1/status` and `worldbrief status`. Contract, backend and Android DTOs all carry the field. | `contract/briefing.schema.json`, `pipeline.py`, `db.py`, `api.py`, Android `BriefingDto.kt`, `Entities.kt`, `Mappers.kt` | `tests/test_states.py` (15 tests), incl. `test_complete_and_partial_briefings_are_distinguishable_everywhere` |
| **WB-004** Story identity | **Changed.** Story id is the briefing date plus the id of the event's earliest report, not its position. | `pipeline.py` (`story_id`) | `test_story_ids_survive_regeneration_in_a_different_order`. The on-phone bookmark check is still to do. |
| **WB-005** Evidence matching | **Changed.** The module now states that overlap is retrieval, and separate rules do the rejecting: negation in the source, negation added, opposite term, names reordered, hedge dropped, unstated cause. The retrieval threshold for claim text was raised from 0.6 to 0.75 after a test showed "treaty was cancelled" being matched to a sentence about the treaty being approved. | `validate.py` | negation, swapped subjects, wrong cause and opposite-meaning tests in `tests/test_adversarial.py` |
| **WB-006** Android compilation | **Not done.** See `STATUS.md`. CI now keeps the full build log and the resolved dependency list as artifacts. | `.github/workflows/ci.yml` | |
| **WB-007** Full local pipeline | **Not done.** See `STATUS.md`. `run --report`, `check-feeds` and `scripts\verify_windows.ps1` exist to record it stage by stage. | `diagnostics.py`, `cli.py` | Report writing is tested with the stand-in only. |

One correction to the review's reading of the first version: `partial` claims were published whether or not the verifier ran; the verifier being unavailable downgraded `supported` claims to `partial`. The fix above replaces that.

## Where a second look would be most useful

1. `validate.py`, `_screen_claim` and the end of `validate_event`. Is there still a path from an unsupported statement to a briefing? The limits known to the author are in `STATUS.md`.
2. Whether the conservative rules remove too much. This can only be judged from a real run's `claim_audit`.
3. `pipeline.py`: what makes a briefing `partial`. Feed failures count; stories dropped because nothing survived checking do not (that is the pipeline working). Is that the right line?
4. `text.py`, `_INJECTION`: the instruction patterns.
5. `android/`: after the first build log exists.

## Evidence in this repository

- `reports/backend-pytest-linux.txt`: full test output.
- `reports/android-kotlin-syntax-check.txt`: what the Kotlin parse check did and did not show.
- To be added from the desktop: `windows-pytest.txt`, `feeds.json`, `real-run.json` and `.md`, `android-build.log`.
