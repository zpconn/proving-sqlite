# C-15 on the legacy-unwind pass: a measurement (Zach's item 7, 2026-11-12)

**MEASUREMENT ONLY.** The orchestrator wrote this harness on the local branch `wip/c15-unwind` (main 0a4f357 merged with orch 9c43df0, which carries the C-17 package's legacy-unwind pass). It is not a proof for merge. A proof replacing C-15's would be a builder's, after a frozen change Zach approves.

## What was measured
- **The harness:** `harness-k4.c` and `Makefile-k4` here (`proofs/C-15/` on the branch), with K=8 in `harness-k8.c` and `Makefile-k8`. One proof, `unwind`:
  - `LOOPS := unwind`, `CONTRACTS := legacy`, `UNWINDSET := sqlite3VdbeRecordUnpack.0:K`. The loop id was checked with `goto-instrument --show-loops`; it is line 92134.
  - The same ENFORCE and REPLACE lists as C-15's merged proofs.
- **SETUP:**
  - `nKey >= 0`, with no upper bound;
  - `capacity <= K`, which becomes `record->nField`;
  - the key is allocated at exactly `(size_t)(nKey > 0 ? nKey : 1) + 8` bytes, the extent the contract's requires reads;
  - the record and its cells are one object of exactly `mem_offset + sizeof(Mem) * capacity` bytes, with `aMem` at `mem_offset`;
  - the KeyInfo is allocated at `sizeof(KeyInfo)`.
- **What the exact symbolic allocation changes:** the end-exact and start-exact shapes of C-15's merged proofs collapse into one. Each object starts at the pointer the function gets and ends where the requires' extent ends.
- **How it was run:** prove.py, so with its 12 GB cap, its 600 s timeout and the gate's checks (proofs/CHECKS), under `nice -n 10`, on lp64-le, ilp32-le and lp64-be.

## Results
| K | lp64-le | ilp32-le | lp64-be | |
|---|---|---|---|---|
| 4 | PASS 80 s | PASS 78 s | PASS 104 s | 2508 properties each, 0 failed (`prove-k4.txt`) |
| 8 | out of memory at 62 s | out of memory at 59 s | out of memory at 65 s | "SAT checker ran out of memory" under prove.py's 12 GB cap (`prove-k8.txt`, `k8-12g-lp64-le.tail.txt`) |
| 8, once under 24 GB | no verdict at 130 s, 22.2 GB peak RSS | not run | not run | 3961 properties ERROR, VERIFICATION ERROR, exit 6 (`k8-24g-*`) |

**K=4 checks:**
- **The unwinding assertion** `sqlite3VdbeRecordUnpack.unwind.1` (line 92134) is present and holds.
- **Planted bugs, lp64-le, mutate.py `--adhoc`:**
  - `pMem++` → `pMem+=2` at 92146, the bug planted before C-15's merge: KILLED, 1481 failed, the first being serialGet's `R_OK(buf, 8)`.
  - `&aKey[d]` → `&aKey[d+1]` at 92143: KILLED, serialGet's requires fails. Reading one byte past the requires' extent is caught, so the key's end is exact.
  - Files: `mutant-*.json` and `mutant-*.log`.
- **Coverage fails:** 26 of 30 lines in each configuration (`coverage-k4.txt`). The four lines are 92134, 92135, 92146 and 92147, and they are an artefact of the legacy-unwind pass (T-018, below). Every line is covered in unwound copies 1 to 3 (`coverage-k4-goals.txt`).

## What bounds this has
- **On lp64-le and lp64-be:** `nField <= 4`, and nKey is any `int` ≥ 0.
- **On ilp32-le, one more limit:** with `--malloc-fail-null` and CBMC's default 8 object bits, an object can't exceed 2^24 − 1 bytes. malloc returns NULL for a larger key, and the harness assumes it isn't NULL. So nKey < 2^24 − 8 there.
  - C-15's merged proofs have nKey ≤ 256, so this is still a much weaker bound.
  - The label would have to state it, unless `OBJECT_BITS` is lowered for that configuration.

## T-018 (found here)
- **What happens:** coverage counts the last unwound copy's dead goals as uncovered lines.
  - prove.py's legacy-unwind pass unwinds with goto-instrument before `cbmc --cover location` adds its goals, so each unwound copy of a block gets goals of its own.
  - With nField ≤ K, the K-th copy always takes the `break`. Its continuing path (`pMem++`, the back edge) and the exit test after it can't run.
  - prove.py marks a line uncovered if any goal on it is unmet, so lines covered in copies 1 to K−1 are reported uncovered.
- **The goals:** blocks 103 and 104, 186 and 187, and 269 and 270 are satisfied; 352 and 353 are not, and neither is 354, the exit test after the last copy.
- **No pass reorder fixes it:** cbmc can't do the unwinding for coverage, because legacy enforcement refuses a function with a loop. "Loops remain in function 'sqlite3VdbeRecordUnpack', assigns clause checking instrumentation cannot be applied" (contracts.cpp:1164).
- **Grouping goals by line set alone is wrong:** distinct blocks can share a line set. The getVarint32 ternary gives 4 blocks with line set {92146} in each copy, and merging them would hide a branch that is dead in every copy.
- **C-17's round 5 meets it too:** all 15 of its proofs are on legacy-unwind.

## For Zach
- **K=4 on legacy-unwind fits the gate with room to spare:** at most 104 s per configuration, against 108 to 256 s for C-15's merged N=256 proofs. It drops the nKey ≤ 256 bound, with the ilp32 caveat above. K=8 doesn't fit.
- **Replacing N=256 would be a later frozen change:**
  - C-15's BOUNDS entry: one proof, no buffers.
  - Rule 16 would have to accept these two allocation sizes, which are expressions of the inputs, not the input locals it allows now.
  - PROPERTIES.md and the label.
  - A builder round for C-15.
- **The prerequisite:** T-018 has to be fixed first, or the builder would have to explain the four lines in NOTES.md.
