# Approval request: T-015's follow-ups, rule 16's tail terms, and freezing proofs/HOWTO.md (2026-11-11)

**Status:** waiting for the auditor's OK on `patch.diff`, which Zach relays. Nothing is applied. The patch is the local branch `wip/t015-followup` against orch. It must land before C-17 merges (Zach and the auditor, evidence/approvals/C-15-bounded/APPROVED.md, follow-ups 1 and 2), and after the C-15-bounded land, on which it builds.

## The changes, against what was asked
| Asked | In the patch | Tests (tool tests `-k bounds`, `-k b2`) |
|---|---|---|
| **1.** T-015's check: a conditional function target (`c: x`) matches only a loop target in a group with the same condition | prove.py `assigns_clause_targets` keeps each target's condition (`1:` counts as none). `legacy_frame_problems` lets an unconditional function target cover the loop's under any condition, and a conditional one only under the same condition. | `n > 1: cells[1].a` in the function, `cells[1].a` in the loop: the build fails ("under the same condition"). The same target under `n > 1:` in both: the check passes. |
| **1.** and a match is refused if the body assigns any identifier the target names | `named_identifiers` (not members, not `__CPROVER_` names) of the target and of its condition; `assigned_in` finds `x =`, compound assignments, `++` and `--` | `if( n>1 ) n = 1;` before the loop, with `cells[n-1].a` verbatim in both: the build fails ("assigns n, which it names") |
| **2.** Rule 16 names the tail terms after `<buffer> + <offset>` in BOUNDS, instead of any constant local | each BOUNDS buffer gains `tails`: C-15's `bytes` none, `allocation` `('mem_offset',)`. Scan allows only those, each a constant local of SETUP. | a constant local not named fails scan; a named one passes. C-15's real harness, in both shapes, still passes. |
| **2.** A BOUNDS comment: each buffer's size equals the largest extent its bounds allow | prove.py, above BOUNDS: why the two shapes and the shift tests need it | (comment) |
| **2.** A constant −1 shift fails the proof, and a +1 shift fails coverage | toy C-94: toySum enforced against `requires(n >= 1 && n <= 8 && r_ok(p, n))`, end-exact over an 8-byte buffer | no shift: prove PASS, coverage 6/6. −1: prove FAIL (27 failed; at n = 8 the pointer leaves the buffer). +1: prove PASS (vacuous), coverage FAIL 0/6. |
| Rule 16's docstring (it still described the first draft) | scan.py's rule 16 text describes the two shapes and the named tail terms | |
| **T-017:** freeze proofs/HOWTO.md | lock.py FROZEN gains `proofs/HOWTO.md`; proof.lock is rewritten when this is applied | `land_paths_problems`: HOWTO.md alone is refused as a frozen change; with an approval record and proof.lock it passes |

## Landing (two parts, T-013 and T-008)
1. Apply `patch.diff` on orch, rewrite proof.lock after committing, add APPROVED.md, and land; the full gate runs. Then restart the daemon on main's campaign.py, which reloads lock.FROZEN.
2. Land HOWTO's "Bounded proofs" section (evidence/approvals/C-15-bounded/HOWTO-bounded-proofs.md) as a frozen change, with its own approval record and proof.lock.

## Not in this patch
- Carrying C-17's bound into C-18 to C-20's labels. It comes with C-17's BOUNDS entry, once its measurements are in (Zach, 2026-11-11; cards C-17 to C-20).

## Results (wip/t015-followup de5bbda; patch.diff is its diff against the merge base e9fca2c)
- **Tool tests:** `RESULT tool-tests PASS 320/320`, including 53 in `-k bounds` (rule 16, native.py, the gate step, results.py's columns, T-015's check and these follow-ups) and the T-017 test.
- **Selftest:** `RESULT selftest PASS 110/110`, run as `env -u TMUX TMUX_TMPDIR=<scratch>`. The live campaign's tmux sessions were intact afterwards.
- **scan.py on the branch:** `RESULT scan PASS 0 problems`. **proof.lock:** 60 files, now with proofs/HOWTO.md.
- **The shift tests, run directly:**
  - no shift: `RESULT prove C-94 lp64-le PASS 0s 42 properties 0 failed` and `RESULT coverage C-94 lp64-le PASS 6/6 lines`;
  - −1: `RESULT prove ... FAIL 0s 48 properties 27 failed`;
  - +1: `RESULT prove ... PASS 0s 48 properties 0 failed` and `RESULT coverage ... FAIL 0/6 lines 6 uncovered 6 unexplained`.
- **`git apply --check`** on orch: clean. 5 files, 155 insertions, 40 deletions.
