# Bounded proofs: how they are built (for builders and reviewers)

This is the section written for proofs/HOWTO.md in patch.diff. A land can't change proofs/HOWTO.md: it is neither frozen nor on campaign.py's land list (T-017). So it lives here until that is fixed, and cards point here.


Only Zach makes a proof bounded, through tools/prove.py's `BOUNDS` (a frozen file; evidence/approvals/C-15-bounded/). A bounded proof proves its property only within the bounds given there, and tests the functions past them natively. scan.py rule 16 checks the mechanics:
- **Any other constant upper bound on an input fails scan, in every proof.** An input is a local passed whole to the call under proof (`id`, `&id`, or `x` in `x + y`), a value assigned to a field of an input object, a local an input is assigned from, or a pointer that aliases an input. Examples are `__CPROVER_assume(n <= 64)`, `!(n > 64)` and `n == 4`. Lower bounds such as `n >= 0` are fine. So are bounds on an allocation's size or a pointer's offset in an unbounded proof (C-01's `extent <= 16`): the reviewer judges whether those narrow anything.
- **In a bounded proof:**
  - SETUP holds each of its bounds as exactly `__CPROVER_assume(<local> <= K);`, once.
  - An allocation's size counts as an input, so it can't carry a constant bound.
  - It allocates no fixed size except one object, `sizeof(T)`: allocations stay exact, as for every proof.
- **The label:** `<card> <proof>: bounded: <what> <= K, ...` appears word for word in the card and in PROPERTIES.md, and RESULTS.md prints it in its Bounds column.
- **Native tests past the bound:** `tests/bounded/<card>-<k>.c` (k 1 to 9) `#include "sqlite3.c"` from unmodified upstream and test the card's functions past the bounds. tools/native.py builds and runs them with campaign.py's repro command (ASan and UBSan) in its sandbox, as a step of every gate that runs the card. A test passes if it exits 0 with no sanitizer report. Sessions don't run the gate, and inside one the sandbox can't start. Compile and run a test yourself to develop it.
