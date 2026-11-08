# How proofs are built here

Bring-up (GOAL.md §1) settled these. The evidence for each is under `evidence/bringup/`.

## A card's directory: `proofs/C-NN/`

- **harness.c.** Its first line of code is `#include "sqlite3.c"`, the overlay, found through `-I`. The proof is one translation unit, so SQLite's internal types (Mem, UnpackedRecord, KeyInfo) and its static functions are visible by their own names. Nothing may be `#define`d before that line. After it come `#include "contracts/<fn>.h"`, `#include "preds.h"` and `#include "spec/record_format.h"` as needed, then one entry function per proof. Assumes go only in a `/* SETUP */ ... /* END SETUP */` block.
- **Makefile.** Variables only, then `include ../Makefile.common`; `tools/prove.py` documents the schema:
  ~~~
  CARD := C-NN
  PROOFS := a b                         # one proof per contract checked: DFCC checks one contract per run
  a_ENTRY := harness_a                  # the harness function
  a_ENFORCE := fn/contract_fn           # at most one
  a_REPLACE := g/contract_g ...         # callees replaced by their contracts
  a_LOOPS := contracts | unwind | none
  a_UNWINDSET := fn.0:10,fn.1:10        # unwinding assertions are always on (proofs/CHECKS)
  a_SOLVER := --smt2 | --z3 | --sat-solver cadical | ...   (optional; quantifiers need --smt2 or --z3)
  a_OBJECT_BITS := 8..16                (optional)
  a_COVER := fn ...                     # functions whose lines coverage reports (default: the ENFORCE function)
  include ../Makefile.common
  ~~~
- **NOTES.md.** Each unreached line is named as `sqlite3.c:<upstream line>`, which `make coverage` checks for.

## Contracts: `proofs/contracts/<fn>.h`

Contracts are clauses on a separate declaration, `contract_<fn>`, with the function's own signature. `--enforce-contract fn/contract_fn` checks `fn` against it, and `--replace-call-with-contract fn/contract_fn` uses it at call sites; both work on static functions. SQLite's text gets only loop annotations. A boundary contract (one for a function no card proves) names its ledger entry in a comment: `Ledger: A-NNN`.

## Loop contracts: PROOF spans in `overlay/sqlite3.c`

`PROOF(__CPROVER_assigns(...) __CPROVER_loop_invariant(...) __CPROVER_decreases(...))`, in that order. Put every character of the span, whitespace included, inside the parentheses: `tools/check_overlay.py` deletes exactly `PROOF(` to its matching `)` and requires upstream to remain.
- **for and while loops:** between the condition's `)` and the body, e.g. `while( i<n )PROOF(...){`.
- **do-while loops:** between `do` and the body: `do PROOF(...){ ... }while( c );`. In CBMC 6.11, clauses after a do-while's condition do not parse, although GOAL.md and agents/builder/GOAL.md §2.6 say to put them there. A do-while invariant is checked before the first iteration, so it must hold at the top of every iteration.
- A loop bounded by construction at 16 iterations or fewer may be unwound instead (`<p>_LOOPS := unwind` and `<p>_UNWINDSET`).

## Running

- `make -C proofs/C-NN prove [CONFIG=lp64-le|ilp32-le|lp64-be]`, `make -C proofs/C-NN coverage`, `tools/mutate.py --card C-NN`, `tools/check_overlay.py`, `tools/scan.py --card C-NN --base main`.
- **Long runs under Codex:** a command's background children are killed when the command returns, even `setsid nohup … &` (evidence/bringup/10-cli.md), so builder §2.9's first option does not work in Codex's sandbox. Run long commands in the foreground with output in a file, e.g. `make -C proofs/C-NN prove CONFIG=lp64-le > /tmp/C-NN-prove.log 2>&1; tail -5 /tmp/C-NN-prove.log`, and let the command run to the end, polling it while it runs. A 15-minute foreground command works this way.
- Each ends with a `RESULT` line. Sessions have `GNUMAKEFLAGS=--no-print-directory` set, so that line is last. Without it, make adds "Leaving directory" after it.
- Building the overlay with goto-cc takes about 6 s per configuration. A proof's CBMC time is separate, and each CBMC run has a 600 s timeout.
- A proof also fails if CBMC reports a function without a body: calls to it would be unconstrained. Replace such a callee with a contract, or let its body run.
- CBMC's malloc may return NULL (`--malloc-may-fail --malloc-fail-null`). Put the NULL check in SETUP: `__CPROVER_assume(p != 0)`.
- Mutants live in `proofs/MUTANTS`; `card=` says which card's proofs must kill each one.
