# How proofs are built here

Bring-up (GOAL.md §1) settled these. The evidence for each is under `evidence/bringup/`.

## A card's directory: `proofs/C-NN/`

- **harness.c.** Its first line of code is `#include "sqlite3.c"`, the overlay, found through `-I`. The proof is one translation unit, so SQLite's internal types (Mem, UnpackedRecord, KeyInfo) and its static functions are visible by their own names. Nothing may be `#define`d before that line. After it come `#include "contracts/<fn>.h"`, `#include "preds.h"` and `#include "spec/record_format.h"` as needed, then one entry function per proof. Each entry function (scan.py checks all of this, checkpoint 0):
  - declares its variables, then has exactly one `/* SETUP */ ... /* END SETUP */` block, then the call under proof as a plain statement (not inside an `if`, loop, `?:`, `&&` or `||`). The call under proof is the ENFORCE function, or for a P2/P3 harness the first call to one of the card's functions.
  - SETUP holds only declarations, `__CPROVER_assume` of sizes, pointers and fields (calling no function but CPROVER primitives such as `__CPROVER_r_ok`), allocations (`p = malloc(n)`), and assignments that read and write no data bytes (no subscripts, no `*p`).
  - No `return` or `goto`; and nowhere in a harness, predicate, spec or contract `abort`, `exit`, `_Exit`, `longjmp`, `__VERIFIER_*` or `__CPROVER_array_set/array_replace/array_copy`. Each ends a path early, which is an assume by another name.
  - A harness that needs no assumption still has an empty SETUP block.
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
- **NOTES.md.** Unreached lines go under the heading `## Unreached lines`, one entry per line of NOTES.md: `- sqlite3.c:<upstream line>: why`, or `- sqlite3.c:<a>-<b>: why` for a range that lies inside one uncovered stretch of the function (uncovered goal lines with no covered goal line between them; `cbmc --cover location` reports one goal per instruction, so this is the source-level block). Every non-blank line under the heading must be such an entry, or `- none`. `make coverage` counts a gap as explained only there, and fails an entry without a reason, one naming more than one line or range, a range that crosses a covered line or runs past the stretch, and an entry naming a line that no proof or configuration of the run leaves uncovered. A line cited elsewhere, such as a caller line in the requires table, explains nothing.
- **Nothing else.** `proofs/C-NN/` holds only these three files (and the ignored build/). Quoted includes resolve against the harness's directory first, so any other file there could shadow a contract; scan.py rejects it, and the gate's include check (`tools/prove.py includes`) fails a harness that pulls in any file but the overlay's sqlite3.c, proofs/{include,contracts,spec}/*.h and system headers. No symlinks anywhere under proofs/, overlay/ or tests/repro/, and no executable files: campaign.py refuses a builder commit with either.
- **COVER.** Every function on the card must be in some proof's COVER (scan.py), so coverage looks at each.

## Contracts: `proofs/contracts/<fn>.h`

Contracts are clauses on a separate declaration, `contract_<fn>`, with the function's own signature. `--enforce-contract fn/contract_fn` checks `fn` against it, and `--replace-call-with-contract fn/contract_fn` uses it at call sites; both work on static functions. SQLite's text gets only loop annotations. A boundary contract (one for a function no card proves) names its ledger entry in a comment: `Ledger: A-NNN`.

## Loop contracts: PROOF spans in `overlay/sqlite3.c`

`PROOF(__CPROVER_assigns(...) __CPROVER_loop_invariant(...) __CPROVER_decreases(...))`, in that order. Put every character of the span, whitespace included, inside the parentheses: `tools/check_overlay.py` deletes exactly `PROOF(` to its matching `)` and requires upstream to remain.
- **for and while loops:** between the condition's `)` and the body, e.g. `while( i<n )PROOF(...){`.
- **do-while loops:** between `do` and the body: `do PROOF(...){ ... }while( c );`. In CBMC 6.11, clauses after a do-while's condition do not parse (GOAL.md §1.3 and builder §2.6 now say so). A do-while invariant is checked before the first iteration, so it must hold at the top of every iteration.
- A loop bounded by construction at 16 iterations or fewer may be unwound instead (`<p>_LOOPS := unwind` and `<p>_UNWINDSET`).

## Running

- `make -C proofs/C-NN prove [CONFIG=lp64-le|ilp32-le|lp64-be]`, `make -C proofs/C-NN coverage`, `tools/mutate.py --card C-NN`, `tools/check_overlay.py`, `tools/scan.py --card C-NN --base main`.
- **Long runs under Codex (builders):** wait once, never poll (builder §2.9). In one exec cell:
  ~~~
  const r = await tools.exec_command({cmd: "make -C proofs/C-NN prove CONFIG=lp64-le > /tmp/C-NN.log 2>&1; tail -5 /tmp/C-NN.log", yield_time_ms: 1000});
  // if r is still running (it has a session_id and no exit code):
  text(await tools.write_stdin({session_id: <its session_id>, chars: "", yield_time_ms: 3600000}));
  ~~~
  sessions.toml sets `background_terminal_max_timeout` and `features.code_mode.default_exec_yield_time_ms` to an hour, so that call, and the cell around it, return when the command exits. A 15-minute command cost 36,925 tokens this way and 748,078 polled once a minute (evidence/bringup/13-checkpoint0.md). Background jobs don't work: the sandbox kills a command's background children when it returns, even `setsid nohup … &` (evidence/bringup/10-cli.md).
- **Long runs under Claude (reviewers):** background with output in a file, or a long timeout. The reviewer's /tmp is private to its session.
- Each ends with a `RESULT` line. Sessions have `GNUMAKEFLAGS=--no-print-directory` set, so that line is last. Without it, make adds "Leaving directory" after it.
- Building the overlay with goto-cc takes about 6 s per configuration. A proof's CBMC time is separate, and each CBMC run has a 600 s timeout.
- A proof also fails if CBMC reports a function without a body: calls to it would be unconstrained. Replace such a callee with a contract, or let its body run.
- CBMC's malloc may return NULL (`--malloc-may-fail --malloc-fail-null`). Put the NULL check in SETUP: `__CPROVER_assume(p != 0)`.
- Mutants live in `proofs/MUTANTS`; `card=` says which card's proofs must kill each one.
