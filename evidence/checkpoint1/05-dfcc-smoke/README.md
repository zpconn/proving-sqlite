# DFCC smoke proofs: every Appendix A function, trivial contracts (checkpoint 1, fix 1)

The audit found that goto-instrument aborts in DFCC for the functions of C-13 to C-15 and C-17 to C-20. The abort is an invariant violation at casting_replace_symbol.cpp:93, on close, read and fcntl64, which os_unix's syscall table refers to. Replacing a callee by its contract doesn't help, because drop-unused-functions runs before DFCC and keeps the callee's body. That body (through vdbeMemClearExternAndSetNull, for sqlite3VdbeMemSetNull) reaches the syscall table.

**The fix** is in tools/prove.py's `build_proof`. After linking and before drop-unused, it runs `goto-instrument --remove-function-body` on two kinds of function:
- every REPLACE function of the proof;
- every callee on the card's `Unreached callees, bodies removed` line (tools/cards.py; only C-13 has one, vdbeMemClearExternAndSetNull).

A removed body that a proof does reach fails that proof: under DFCC as "undefined function should be unreachable", and without DFCC as a function with no body. Tool tests (`-k dfcc`):
- a toy with os_unix's table shape, which aborts on 71447f2;
- a reached unreached-callee, which fails;
- a REPLACEd callee, which passes;
- a card that lists its own function as an unreached callee, which is rejected.

All four fail on 71447f2.

**This run.**
- `gen.py` writes `proofs/C-NN/{harness.c,Makefile}`, one proof per Appendix A function (22 functions, 18 card directories).
- Each proof ENFORCEs `contract_<fn>` with `__CPROVER_ensures(1)`.
- It REPLACEs every direct callee from evidence/checkpoint1/callgraph.txt with a trivial contract. The boundary callees are replaced by the real headers in proofs/contracts/ (LEDGER.md A-002 to A-004).
- Pointers are malloc'd, and everything else is nondet. Loops are unwound to 2, and CBMC's memcmp loop to 17. C-17 needs `OBJECT_BITS := 12`.
- The proofs are tooling tests, not proofs of anything: the failures are expected, since a trivial contract checks nothing about inputs.
- They were run with `tools/prove.py prove --card-dir <dir> --config all --overlay overlay`.

**Result** (`results.txt`):
- After the fix, every one of the 22 runs through link, body removal, drop-unused, the argument-type check, DFCC, slice-global-inits and CBMC, on lp64-le, ilp32-le and lp64-be, with the same property counts on all three.
- 71447f2's prove.py, on the same harnesses on lp64-le, aborts in DFCC with the invariant violation for exactly the seven:
  - sqlite3VdbeMemSetNull (C-13);
  - sqlite3VdbeAllocUnpackedRecord (C-14);
  - sqlite3VdbeRecordUnpack (C-15);
  - sqlite3VdbeRecordCompareWithSkip (C-17);
  - sqlite3VdbeRecordCompare (C-18);
  - vdbeRecordCompareString (C-19);
  - vdbeRecordCompareInt (C-20).

  C-16, rerun as a control, runs on both.
