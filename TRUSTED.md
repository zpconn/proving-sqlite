# TRUSTED

What milestone 1's *proved* claims rest on without proving it (AGENTS.md §4). If one of these is wrong, a proof here can pass while the property fails. Each is used as listed, at the versions in pin.txt and evidence/bringup/01-pins.md.

## CBMC 6.11.0 (cbmc-6.11.0)

- **Its C semantics.** goto-cc's front end, run as `goto-cc <CONFIGS flags> -include proof.h -I overlay -I proofs/include -I proofs` (tools/prove.py), and CBMC's model of C11 on each configuration. That model covers integer widths, two's complement, IEEE 754 doubles, byte order and pointer size. It also covers the meaning of every check in proofs/CHECKS. The configurations were probed (evidence/bringup/05-configs.md, `make probe`), and each check was shown to fire on a toy (evidence/bringup/toys/04-checks/). Those probes are tested evidence, not proofs of the front end.
- **Its transformations:**
  - `--remove-function-body`, before drop-unused, on each REPLACE function and each callee on a card's "Unreached callees, bodies removed" line (checkpoint 1, fix 1): that a call reached to a removed body fails the proof (under DFCC, "undefined function should be unreachable"; without it, a function with no body, which prove.py fails) rather than being skipped;
  - `--drop-unused-functions` and its function-pointer removal;
  - `--dfcc` with `--enforce-contract`, `--replace-call-with-contract` and `--apply-loop-contracts`: replacing a callee by its contract is sound only if DFCC checks the contract's requires at each call and assumes no more than its ensures;
  - `--slice-global-inits`;
  - **CBMC's legacy contracts, a second contracts implementation** (T-006; Zach, 2026-11-10, evidence/approvals/T-006-dfcc-loop-pointer/):
    - **Which proofs:** only those whose Makefile sets `<name>_CONTRACTS := legacy`, and only on cards C-15 (sqlite3VdbeRecordUnpack) and C-17 (sqlite3VdbeRecordCompareWithSkip, if its proof hits T-006), the cards in tools/prove.py's LEGACY_CARDS. Every other proof uses DFCC. RESULTS.md's rows for those proofs rest on this engine.
    - **Trusted the way DFCC is:**
      - `--replace-call-with-contract f` checks f's requires at each call, havocs what its assigns names and assumes no more than its ensures;
      - `--apply-loop-contracts` checks each invariant on entry and after each iteration, its decreases, and that the loop writes only what its assigns lists, callees' contracts included;
      - `--enforce-contract f` checks f's ensures and assigns under its requires.
    - **Pass order:** prove.py runs them in that order, replace, then loops, then enforce. With loops applied before the replacement, a replaced callee whose body is removed can write outside the loop's assigns unchecked, which the callee-frame toy shows.
    - **Contract text:** the legacy engine reads clauses only from a function's own declaration. So each legacy contract is its proofs/contracts/<fn>.h `contract_<fn>` declaration with only the name changed, generated at every build, with no stored copy.
    - **Static locals:** a replaced callee with a static local, called in a loop, aborts the enforce pass (T-012). Such a callee keeps its body, and prove.py says so. For C-15 that is sqlite3VdbeSerialGet.
    - **Kept callee bodies:** loop frames are checked against kept callee bodies too. A callee called in the loop with its body kept, writing outside the loop's assigns, fails by "Check that … is assignable" inside the callee (tool tests `-k b2`).
    - **Loop frames against the function's (T-015; Zach, 2026-11-11, evidence/approvals/C-15-bounded/):** the legacy engine checks a write inside a contracted loop against that loop's assigns only. It never checks the loop's frame against the function's assigns; DFCC does ("Check assigns clause inclusion for loop"). A loop whose frame is wider than the function's could therefore write outside the function's frame unchecked: the T-015 toy, evidence/orchestrator/tool-issues/T-015/. So prove.py fails a legacy build unless every assigns target of a loop in an enforced function is a local or parameter of that function, or appears verbatim among the targets of its contract's assigns. A conditional target there (`c: x`) matches only a loop target under the same condition, and a match is refused if the function's body assigns a variable the target or its condition names (T-015 follow-up). The check is textual: it doesn't see the body write through a member or an address the target depends on, such as `p->a = x` before a loop whose target is `p->a[0].x`, or `g(&p)`. The legacy proof's reviewer checks those. In C-17 it doesn't arise: the body writes only pPKey2->errCode and pPKey2->eqSeen, and takes no parameter's address (the auditor, 2026-11-11). Within that frame, CBMC's own check catches a write outside it (tool tests `-k bounds`, T-015). A card in prove.py's LEGACY_FRAME_ARGUED argues the inclusion instead, checked by its reviewer: C-15, whose frame is whole Mem cells (below, Reviewed, not proved). RESULTS.md's Assigns column then reads "reviewed (T-015)". A pin test keeps the engine's present behaviour on record, so a CBMC that closes the gap shows up.
    - **Clause placement:** contract clauses count only on a proofs/contracts/<fn>.h `contract_<fn>` declaration. prove.py fails any build whose proofs/include/ headers carry a clause, or whose contracts headers put one on another name, and scan.py rejects such headers (B2). prove.py's textual check misses a clause hidden in a one-line `#define`; scan.py's rule 15 (no #define in shared headers but the include guard) is the guard for that form, and DFCC ignores such a clause.
    - **Validated on toys** (tool tests `-k legacy`, tools/tests/legacy/), each failing by the expected check:
      - a replaced call forgets what its contract assigns;
      - a callee assigning outside the loop's frame;
      - a write through an alias outside it;
      - an invariant true at entry but not preserved;
      - a wrong decreases;
      - a claim after the loop that the invariant doesn't support;
      - an out-of-bounds write in the loop;
      - an out-of-bounds pointer to a replaced callee;
      - T-003's flexible array, with an exact allocation;
      - aliased arguments to an `is_fresh` contract, while separate ones prove.
    - **The same as DFCC in two respects:** globals start unconstrained, and T-003's bounds gap is the same, because both engines share the bounds instrumentation (a one-byte-short element read in a legacy-enforced function passes; evidence/approvals/T-006-dfcc-loop-pointer/flexgap.c).
  - unwinding with `--unwinding-assertions`.
- **A known false failure in `--conversion-check`** (C-11, evidence/approvals/C-11-f2i-exact-min/): for a conversion from a floating type to a signed integer type of width w, CBMC 6.11 reports the exact minimum −2^(w−1) as overflowing whenever the floating type cannot represent −2^(w−1)−1: double to a 64-bit type, float to a 32-bit type. Its check reads `r > -9.223372e+18 && r < 9.223372e+18` for (i64)r. On toys, the next double below −2^63 and 2^63 itself are still flagged, and double to 32-bit is exact. So this rejects one defined input and misses none. In scope it applies only at sqlite3IntFloatCompare 92434, the one float-to-integer conversion in Appendix A; that input is argued in UB-CLASSES.md.
- **A known gap in `--bounds-check`** (C-16, evidence/orchestrator/tool-issues.md T-003; evidence/approvals/T-003-flexarray-bounds/): CBMC 6.11 checks an element of a flexible array member, read or written as `s->a[k]`, only where it starts. A read of `pKeyInfo->aColl[0]` from a KeyInfo one byte short of SZ_KEYINFO(1) passes, though it overflows, as ASan shows natively. The same element through a pointer is caught, and so are heap arrays, struct members and a flexible array with no element. `__CPROVER_r_ok` checks the whole range. A proof that touches such an array is sound only if both of these hold, and its reviewer checks both:
  1. every footprint over the array is stated in whole elements, as in `r_ok(pKeyInfo, SZ_KEYINFO(n))`;
  2. the harness allocates the object at exactly that size (`__CPROVER_is_fresh` or `malloc` of SZ_KEYINFO(n) bytes, never larger), so a read of element n starts out of bounds and CBMC catches it.
  NOTES.md shows a read one element past the end fails. The "minus one fails" evidence for those footprints is minus one element in CBMC (proved) and minus one byte natively under ASan (tested). In scope: KeyInfo.aColl at 93045 (C-16), 92730 and 92736 (C-17).
  - Under DFCC, statics and globals start unconstrained (proofs/HOWTO.md), which over-approximates SQLite's initialized globals.
- **Its back ends:** the default SAT solver, MiniSat 2, unless a card's Makefile names another (`<name>_SOLVER`: CaDiCaL, Glucose, or Z3 4.8.12 through `--smt2`/`--z3`). No merged proof names one.
- **Coverage:** `cbmc --cover location`, which the gate uses to require that proofs reach every line of the functions under proof (tools/prove.py coverage). Under the legacy engine an enforced function's body is `__CPROVER_contracts_original_<fn>`, with kept callees' bodies inlined into it, so coverage counts only the source lines of the function itself there (C-15 round 4; tool tests `-k legacy`).
- **Its library models,** used in place of the C library:
  - `memcpy`: serialGet (91976), serialGet7 (91989), sqlite3IsNaN (36449);
  - `memcmp`: sqlite3VdbeRecordCompareWithSkip (92739, 92767), vdbeRecordCompareString (92975). Where C-17 and C-19 replace those calls with LEDGER.md A-006's boundary contract (proofs/contracts/memcmp.h, B2), the model is not used and the contract is *assumed*;
  - `malloc` and `free`, under `--malloc-may-fail --malloc-fail-null`: harnesses only.

  Under `--pointer-check`, each model checks that its arguments are accessible for the length it is given. It also checks that memcpy's source and destination don't overlap (UB-CLASSES.md).

## The preprocessor and headers

- **GCC 13.3.0's preprocessor**, which goto-cc runs (`gcc (goto-cc 6.11.0 (cbmc-6.11.0)) 13.3.0`), with the system headers of Ubuntu 24.04 and gcc-multilib for ilp32-le. The include check (`prove.py includes`, in the gate) shows each harness pulls in nothing but overlay/sqlite3.c, proofs/{include,contracts,spec}/*.h and system headers. Which code survives `#if` is the preprocessor's decision under the default compile options (UB-CLASSES.md, Out of scope).
- **The configuration flags** in proofs/CONFIGS (`-m64`, `-m32`, `--big-endian -DSQLITE_BYTEORDER=4321 -funsigned-char`): that they make goto-cc and CBMC model the platform each name says, which `make probe` checks for word size, byte order, char signedness and SQLite's branch choice.

## Reviewed, not proved

These are not trusted the way CBMC is. They are checked by review, and what they say is a premise of a proved claim:
- **C-15's contract frame** (T-015): sqlite3VdbeRecordUnpack's assigns, whole Mem cells `aMem[0..nField)` with `default_rc` and `nField`, contain its loop's frame `object_from(pMem)` by the exact layout. The legacy engine doesn't check that inclusion; C-15's reviewer does. Its seven-member frame (`u`, `z`, `n`, `flags`, `enc`, `db`, `szMalloc`) is *tested* natively by tests/bounded/C-15-*.c, which checks every other Mem byte is unchanged.
- **Native tests past a bounded proof's bounds** (tests/bounded/, PROPERTIES.md change 8): *tested*, not proved, under GCC 13.3.0's AddressSanitizer and UndefinedBehaviorSanitizer on lp64-le, run by tools/native.py in campaign.py's repro sandbox as a gate step.
- **proofs/spec/record_format.h,** the P3 reference: written from SQLite's file format document (evidence/spec/fileformat2.html, hashed in evidence/spec/README.md) and checked against it row by row by a Codex session (reviews/spec-r1.md, APPROVE). A native comparison with sqlite3VdbeSerialGet is tested evidence (evidence/spec/README.md).
- **UB-CLASSES.md's argued rows:** the kinds of UB CHECKS does not catch, argued by inspection and re-checked by each card's reviewer.
- **The project's tools,** frozen with tools/ at checkpoint 1:
  - check_overlay.py (the overlay is upstream plus PROOF spans);
  - scan.py (harness discipline);
  - prove.py (the pipeline above, and the card-call argument types);
  - mutate.py, gate.py and lock.py.

  A wrong tool could pass a vacuous proof. Each tool rule has a tool test that fails without it (tools/tests/test_tools.py; evidence/bringup/13-tool-tests.txt).

What is *assumed* rather than trusted is in LEDGER.md: the boundary contracts and the callers' obligations.
