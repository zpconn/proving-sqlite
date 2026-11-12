# Approval request: C-15's bounded P1, the tools it needs, and T-015's frame check (2026-11-11)

**Status:** waiting for the auditor's OK on `patch.diff`, which Zach relays. Nothing is applied. The patch is the local branch `wip/bounds` against orch (merge base 72238ff).

## Zach's decisions (2026-11-11), and where each is met
| Decision | In the patch | Evidence |
|---|---|---|
| Bounds K=4, N=256, final once the encoding diagnostic reports | tools/prove.py `BOUNDS['C-15']`: `capacity <= 4` (p->nField), `nKey <= 256` | `diagnostic/`: no option reaches K=8 within 600 s (below) |
| Labelled bounded in PROPERTIES.md, RESULTS.md and the card | PROPERTIES.md change 8; results.py's Bounds column; cards/C-15.md; scan rule 16 requires the label word for word in the card and PROPERTIES.md | tool tests `-k bounds` |
| Two variants: end-exact, and start-exact with both offsets 0; both pass on all three configurations | `BOUNDS['C-15']` has `unpack` (exact: end) and `unpack_start` (exact: start), with the buffers `bytes = malloc(256 + 8)` and `allocation = malloc(mem_offset + sizeof(Mem) * 4)` and their offsets | end-exact: reports/C-15-b4.md (290, 107 and 245 s); start-exact: `start-exact/` (203, 108 and 182 s); every run 1,757 to 1,759 properties, 0 failed |
| Scan rule 16 allows exactly two shapes: a constant-size buffer, with a pointer offset of 0 or (buffer size minus the exact requires extent) | scan.py `check_bounded_allocations` | `-k bounds`: wrong offset either way, the offset set twice, another offset, another size, a variable size, an undeclared allocation, all rejected |
| A planted underread that passes the end-exact variant and fails the start-exact one | `-k bounds`, toy card C-93 (`toyPeek` with `PLANT_UNDER`), run through prove.py | underread: end PASS, start FAIL; overread: end FAIL, start PASS; no plant: both PASS |
| T-015 for C-15: assigns as whole Mem cells, a native frame test, TRUSTED.md, a toy that pins the behaviour | prove.py `LEGACY_FRAME_ARGUED['C-15']`; TRUSTED.md (legacy section, and "Reviewed, not proved"); C-15's card for round 5 | `-k bounds` "T-015 pin"; the native test's seven-member frame check |
| T-015 for C-17: prove.py fails a legacy build unless each loop assigns target is a local of the function or verbatim among its assigns targets; shown on T-015's toy | prove.py `legacy_frame_problems`, in `build_proof` | `-k bounds`: the bad toy (`object_from(p)`) fails the build; the good one (`cells[0].a, cells[n-1].a`) passes and proves; with that frame, a write to `b` fails CBMC's own check |
| RESULTS.md labels legacy assigns "reviewed" until the check exists | results.py's Assigns column: "proved", or "reviewed (T-015)" for LEGACY_FRAME_ARGUED cards (C-15). The check lands in this patch, so C-17 gets "proved" only by passing it | `-k bounds` |
| One request with wip/bounds, A-007 and tests/bounded/ | all of the below; tests/bounded/: see "Not in the patch" | |

## What `patch.diff` does
| File | Frozen | Change |
|---|---|---|
| tools/prove.py | yes | `BOUNDS` (C-15's two proofs, their bounds and buffers) and `bounds_label`. T-015's `legacy_frame_problems`, run on every legacy build with loop contracts, except for `LEGACY_FRAME_ARGUED` (C-15). Coverage under legacy: the enforced body's legacy name, `__CPROVER_contracts_original_<fn>`, counting only the function's own lines, since kept callees are inlined into it (my T-006 error: coverage failed for every legacy proof). |
| tools/scan.py | yes | **Rule 16:** any constant upper bound on an input of the call under proof fails unless BOUNDS gives it, through fields, aliases, copies, negations and either operand order. A bounded proof holds each bound as its own assume and allocates only `sizeof(T)` objects and its BOUNDS buffers, in the two shapes. Labels are required in the card and PROPERTIES.md. Native tests are required once proofs/<card>/ exists. tests/bounded/ holds only `<card>-<k>.c`, with no symlinks (rule 12). |
| tools/results.py | yes | Bounds and Assigns columns in results.csv and RESULTS.md. Every merged row gains them at the next merge, when campaign.py regenerates both files. |
| tools/native.py | yes, new | Builds and runs tests/bounded/<card>-<k>.c with campaign.py's repro command (ASan, UBSan, unmodified upstream) in its sandbox. A test passes if it exits 0 with no sanitizer report. |
| tools/gate.py | yes | A `native C-NN` step for every bounded card the gate runs. |
| tools/tests/test_tools.py | yes | `-k bounds` (45 tests) and `-k legacy` (the coverage test); the repo-copy scan test also copies PROPERTIES.md. |
| PROPERTIES.md | yes | Change 8: P1 for sqlite3VdbeRecordUnpack is bounded, in two proofs, with the labels; *tested* past the bounds; the frame *reviewed*. |
| TRUSTED.md | yes | The legacy section gains T-015 and the frame check. Coverage under legacy. "Reviewed, not proved" gains C-15's frame and the native tests. |
| LEDGER.md | no | **A-007**, the builder's draft: the record and its cells as one block, aligned, with a positive capacity, separate from the inputs (C-15's requires besides A-001). |
| cards/C-15.md | no | Round 5: the labels, the two shapes in canonical form, the whole-cell frame, the native tests, coverage, A-007, the merge conditions. M-063 is added, and the T-006 probe's sentence now states its bounds. |
| proofs/HOWTO.md | no | "Bounded proofs". |

## Evidence
- **The encoding diagnostic** (`diagnostic/`; the branch wip/c15-encoding): K=8, N=256 on lp64-le, the builder's round-4 harness set by its configure.py, every run capped at 12 GB.

  | Run | Time | Peak RSS | Verdict |
  |---|---:|---:|---|
  | default solver, `prove.py --timeout 3600` | 1,036 s (CBMC 1,020 s) | 7.6 GiB | PASS, 1,787 properties, 0 failed |
  | `--sat-solver cadical` | 30 s | 11.7 GiB | out of memory in propositional reduction (1,095 ERROR) |
  | `--arrays-uf-always` | 1 s | 0.1 GiB | CBMC crash: invariant at arrays.cpp:211 (T-016); no verdict |
  | `--refine-arrays` | 984 s | 7.9 GiB | VERIFICATION SUCCESSFUL, 1,787 |

  None reaches K >= 8 within 600 s, so no solver change is proposed; K=4, N=256 stands. Raising the gate's 600 s limit isn't proposed: that would be a frozen change to prove.py with its own approval record.
- **The start-exact measurement** (`start-exact/`; the branch wip/c15-start): the builder's harness with both offsets 0 and the bounds as their own assumes, K=4, N=256, through prove.py (12 GB, 600 s). It passes on lp64-le in 203 s (3.7 GiB), ilp32-le in 108 s (2.4 GiB) and lp64-be in 182 s (3.7 GiB), each with 1,757 properties and 0 failed. This is a measurement; round 5's builder writes the variant.
- **Scan rule 16 on C-15's real harness:**
  - The round-4 text is refused for three reasons: the nKey bound sits in a conjunction, the end-exact offsets aren't in the canonical form, and that bound is then undeclared.
  - The canonical end-exact form passes as `unpack`.
  - The start-exact form passes as `unpack_start`, and is refused as `unpack`.
  - All 15 merged cards pass unchanged.
- **The native test** (`native/C-15-1.txt`): the builder's round-4 prototype, evidence/orchestrator/C-15-b4/native.c, run unchanged through native.py in the sandbox. It gives "RESULT native PASS 1414 cases, 1362 beyond proposed bounds" in 26 s. It checks every Mem byte outside the seven written members.
- **T-015** (evidence/orchestrator/tool-issues.md, tool-issues/T-015/): reproduced under legacy and DFCC, with two other pass orders.
- **Tool tests and selftest:** see "Results" below.

## Not in the patch, and why
- **tests/bounded/C-15-1.c.** LAND_ALLOWED in campaign.py has no tests/bounded/, and a land that adds it would be judged by the old rules (T-013). So C-15's round-5 builder commits its own prototype there; it's on the card's May change line. Scan requires the test once proofs/C-15/ exists, so every C-15 gate needs it.
- **results.csv and RESULTS.md.** campaign.py regenerates them at each merge, and a land may not carry them.

## After the OK
1. Apply `patch.diff` on orch, rewrite proof.lock after committing, add APPROVED.md, and land. Frozen files change, so the full gate runs.
2. **C-17:** its legacy proof must now pass the frame check. Its round-4 builder (J0092) started before this, so if its loop frame fails the check, the gate sends it to triage.
3. Retry C-15 for round 5, with the card's notes. Before merge: M-050, M-051 and M-063 killed under the bounds, my `--adhoc` planted bug caught, and the reviewer's checks.

## Results (on wip/bounds 5111466)
- **Tool tests:** `RESULT tool-tests PASS 311/311`. Of these, 45 are rule 16, native.py, the gate step, results.py's columns and T-015's check (`-k bounds`), and 21 are `-k legacy`, the coverage test included. The coverage test fails on the old prove.py ("no coverage goals found for t_static").
- **Selftest:** `RESULT selftest PASS 110/110`, run as `env -u TMUX TMUX_TMPDIR=<scratch> tools/campaign.py selftest`. The live campaign's tmux sessions were intact afterwards.
- **scan.py on the branch:** `RESULT scan PASS 0 problems` (15 card directories). `tools/results.py --check` passes once results are regenerated (63 rows), which campaign.py does at the next merge.
- **`git apply --check`** on orch: clean. 11 files, 963 insertions, 23 deletions.
