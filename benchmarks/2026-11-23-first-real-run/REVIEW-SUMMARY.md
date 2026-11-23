# Claim review summary: first real run, 2026-11-23

Every published claim was read against its stored source text. The claim-by-claim table is kept on the desktop beside this file (`claim-review.md`, not in Git because it contains the news text).

Reviewer: Claude. One reviewer, and the same one who wrote the verification rules, so this is a first pass and not an independent audit (see WB-009).

## Published as supported: 21

| Verdict | Count |
|---|---|
| Correct | 16 |
| Attribution dropped: a report's or correspondent's finding stated as plain fact | 3 |
| Opinion published as fact: source was an opinion column | 2 |

So 5 of 21 "supported" claims should not have been published as plain fact: a false-approval rate of 24 % on this sample. None was a fabrication; all five say what their source says, but drop who said it or come from commentary.

## Published as partly confirmed: 5

| Verdict | Count |
|---|---|
| Flag justified: the claim added something the source did not say | 2 |
| Flag unnecessary | 2 |
| Debatable | 1 |

## Removed: 3

| Verdict | Count |
|---|---|
| Wrong removal (true to its source, removed by the name-order rule) | 2 |
| Debatable (accurate, but relied on the outlet's name in the passage label) | 1 |

An earlier status note said the model had invented one of these. That was wrong: the outlet did report that figure.

## What was changed as a result

| Finding | Change | Regression test |
|---|---|---|
| Opinion as fact (2) | Opinion, live pages and sport are excluded; analysis and explainers are never a source of claims | `test_opinion_column_is_never_a_source_of_claims`, `test_article_kinds` |
| Attribution dropped (3) | A claim with no attribution whose source sentence has one is marked partly confirmed | `test_dropped_attribution_is_flagged` |
| Wrong removals (2) | Name order alone no longer removes a claim; the names must trade places around the same words | `test_reordered_names_without_a_role_swap_are_no_longer_removed`, `test_a_real_role_swap_is_still_removed` |
| Unnecessary flags (2) | Alternative names of a country the source mentions are accepted; qualifiers are read only from the part of the sentence the claim draws on | `test_another_name_for_the_same_country_is_not_a_new_name`, `test_attributed_claim_is_not_penalised_for_the_sources_claiming` |
| Wrong quote shown | Over-long run-on passages are cut into windows before matching | `test_quote_comes_from_the_right_part_of_a_run_on_passage` |

Whether these changes hold on real output is not yet known: they are tested on written examples of each error shape, not on a second real run.
