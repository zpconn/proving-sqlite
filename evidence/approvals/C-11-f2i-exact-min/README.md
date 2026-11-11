# Approval request: C-11, CBMC's float-to-int check at r = −2^63 (2026-11-10)

**Status: unapplied, waiting for Zach** (GOAL.md §0.3). C-11 is parked; C-17 to C-20 wait on it.

## The problem
- C-11's builder (round 1, `C-11-b1.md`, NEEDS-DECISION) proved sqlite3IsNaN on all three configurations.
- sqlite3IntFloatCompare fails on every configuration, and only on one property: `sqlite3IntFloatCompare.overflow.1`, the `%float-to-int` pass's check of `y = (i64)r` at upstream/sqlite3.c:92434. The counterexample is r = 0xc3e0000000000000 = −2^63.
- The guards at 92432–92433 let exactly [−2^63, 2^63) through, and NaN is excluded at 92426.
- At −2^63 the integral part is INT64_MIN, so C11 6.3.1.4p1 defines the conversion. **The failure is CBMC's, not SQLite's.**

## Evidence (this directory; `run.sh` reruns it)
- **`toy.c`, `toy.txt`, `toy-exact_min.out`**: CBMC 6.11.0 with `--conversion-check`. Its check for (i64)r reads `r > -9.223372e+18 && r < 9.223372e+18`, consistent with a lower bound of −2^63−1 that rounds to −2^63 in double, then a strict `>`. This is the measured behaviour; CBMC's source was not read.

  | Conversion | C11 | CBMC 6.11 |
  |---|---|---|
  | (i64)(−2^63) | defined | FAILED |
  | (i64)(next double below −2^63) | UB | FAILED |
  | (i64)(2^63) | UB | FAILED |
  | (i64)(largest double below 2^63) | defined | SUCCESSFUL |
  | (int)(float)(−2^31) | defined | FAILED |
  | (int)(double)(−2^31) | defined | SUCCESSFUL |

  So the check rejects the exact minimum when the float type can't hold −2^(w−1)−1. It still flags every value that is UB.
- **`boundary.c`, `native.txt`**: *tested*, not proved. sqlite3IntFloatCompare(i, −2^63) was run against unmodified upstream/sqlite3.c under ASan, UBSan and float-cast-overflow, for six values of i (0, ±1, INT64_MIN, INT64_MIN+1, INT64_MAX). There was no diagnostic and every result was as expected. Control (`control.c`): UBSan does flag (long long) of the next double below −2^63.
- **Mutants:** C-11's M-042 (`>=` to `>` at 92433, which lets 2^63 through) and M-043 (the lower guard moved one double down) are each killed by a value CBMC still flags correctly. Excluding exactly −2^63 therefore kills no fewer mutants.

## Options
1. **Recommended: argue that one input.** `patch.diff`, 5 files:
   - UB-CLASSES.md: an argued row for 92434 at r = −2^63, and the checked row names its one exception;
   - TRUSTED.md: the false failure, with its toy evidence;
   - PROPERTIES.md: change 7, under which P1 is proved for every (i, r) but r = −2^63, and argued and tested there;
   - cards/C-11.md: the harness may assume `r != -0x1p63` in SETUP and nothing else about r or i, and must show that without it only the 92434 property fails, with −2^63 in the trace;
   - proof.lock, for the three frozen files.

   No tool changes. At that input the rest of the function is i64 comparisons, `(double)i` and double comparisons, so the proof would show nothing more there than the argument does. Tool tests `-k docs`, `-k lock` and `-k scan` pass with the patch (8/8, 9/9, 139/139), as do `lock.py check` and `scan.py`.
2. **A tool exception.** prove.py (frozen) would accept a failed float-to-int property in a second proof whose SETUP pins r == −0x1p63, checked against the trace value and limited to sites listed in proofs/CHECKS. That proves the other checks at that input, but they are trivial there, and it adds tool code to the trusted path. I'd write it only if you prefer it.
3. **A CBMC with a corrected check.** This changes the trusted base and pin.txt, and every proof would rerun. A fixed release isn't known to exist, and the machine has no network to look for one.

**Recommendation:** option 1. On a yes, I apply `patch.diff` on orch and land it with proof.lock; campaign.py then runs the full gate. Then I run `tools/campaign.py retry C-11`.
