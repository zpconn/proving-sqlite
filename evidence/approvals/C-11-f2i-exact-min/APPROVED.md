# Approval: C-11, option 1, with one addition (Zach, 2026-11-10)

Zach's answer, verbatim:

> C-11: option 1, approved, with one addition. The harness assume r != -0x1p63 also removes that input from the enforcement of contract_sqlite3IntFloatCompare, which C-17 uses at every r. So the UB-CLASSES row, change 7 and C-11's NOTES.md must also argue that the contract holds at r = -2^63: every return there is +1, -1 or the final ternary (-1, 0 or 1), assigns() holds since nothing is written, and the native run checks the value for six i. Say "proved for every other (i, r); argued and tested at r = -2^63" wherever sqlite3IntFloatCompare's result is stated, RESULTS.md included. The reviewer must confirm the assume is exactly `r != -0x1p63` and the only constraint on r or i, and that without it the proof fails only on the float-to-int property at 92434 with r = -2^63 in the trace. Land the patch with its approval record and proof.lock as §0.3 says, then send C-11 back for its round.

## What was applied

Applied on orch and landed in one land with proof.lock: README.md's `patch.diff`, plus the addition.

| File | Frozen | Change |
|---|---|---|
| UB-CLASSES.md | yes | The checked 6.3.1.4p1 row names its one exception. The new argued row for 92434 at r = −2^63 also argues contract_sqlite3IntFloatCompare at that input: it returns +1 (92436) or 0 from the final ternary (92440, for i = INT64_MIN), the ternary gives only −1, 0 or 1, and nothing is written. The row ends "proved for every other (i, r); argued and tested at r = −2^63". |
| TRUSTED.md | yes | CBMC 6.11's `--conversion-check` false failure at −2^(w−1), with the toy evidence. |
| PROPERTIES.md | yes | Change 7, which covers the contract and gives the wording, RESULTS.md included. |
| tools/results.py | yes | **The addition's RESULTS.md part.** RESULTS.md's header said "Every row is *proved*", and the generator had no way to qualify a row. A fixed `ARGUED` entry for sqlite3IntFloatCompare now drives an *Argued* column in RESULTS.md and an `argued` column in results.csv. It is filled for a proof that covers the function, and for one that uses its contract (C-17's, say). The header says the Argued column is *argued* and *tested*, not *proved*. The entry lives in a frozen file so no card edit can drop it. |
| tools/tests/test_tools.py | yes | `-k results`: four tests, which fail on main's results.py (no `argued_notes`). |
| cards/C-11.md | no | The harness may assume `r != -0x1p63`, nothing else about r or i. NOTES.md argues the contract at r = −2^63 and uses the wording. The reviewer confirms the assume and the failure without it. |
| proof.lock | n/a | Rewritten for the frozen files above. |

results.csv and RESULTS.md themselves are campaign.py's to regenerate at the next merge; a land may not touch them. Until then, the committed results.csv lacks the new column, and `tools/results.py --check` reports the difference. The gate does not run that check; §5 runs it after the last regeneration.
