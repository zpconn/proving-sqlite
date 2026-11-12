# How proofs are built here

Bring-up (GOAL.md §1) settled these. The evidence for each is under `evidence/bringup/`.

## A card's directory: `proofs/C-NN/`

- **harness.c.** Its first line of code is `#include "sqlite3.c"`, the overlay, found through `-I`. The proof is one translation unit, so SQLite's internal types (Mem, UnpackedRecord, KeyInfo) and its static functions are visible by their own names. Nothing may be `#define`d before that line. After it come `#include "contracts/<fn>.h"`, `#include "preds.h"` and `#include "spec/record_format.h"` as needed, then one entry function per proof. Each entry function (scan.py checks all of this, checkpoint 0):
  - declares its variables as plain locals (no `static`, `extern` or `_Thread_local` in an entry function), written with C keywords and typedef names only (`u8`, `u64`, `size_t`, `unsigned char`), never a name sqlite3.c, proof.h or an included header #defines (`SQLITE_PRIVATE` is `static`, `SQLITE_EXTERN` is `extern`; use `_Bool`, not `<stdbool.h>`'s `bool`), then has exactly one `/* SETUP */ ... /* END SETUP */` block, then the call under proof as a plain statement (not inside an `if`, loop, `?:`, `&&` or `||`). The call under proof is the ENFORCE function, or for a P2/P3 harness the first call to one of the card's functions. Between END SETUP and that call stand only declarations and snapshots: no other stores, assignments, calls or control flow. A snapshot copies inputs into a local array so the harness can compare after the call, and has exactly this form: `S[k] = X[k];` with a constant k, or `for(i = 0; i < 9; ++i) S[i] = X[i];` (constant bounds, `++i`, that one statement, no braces). S is an array declared in the entry function (not a pointer, not static, no initializer); i is a plain local declared there and used by no other snapshot loop; neither S nor i appears in the call's statement or in SETUP.
  - every call to one of the card's functions, or to a SQLite macro that expands to one (`getVarint32`, `putVarint32`), is in an entry function, anywhere in it (after the call under proof and inside asserts too), and each argument is an identifier, `&x` or `p + k`, where p is a data pointer and k a different identifier; every name in an argument is a local variable the entry function declares before or in SETUP, never a macro, enum constant or global (`SQLITE_ROW`, `sqlite3PendingByte`): `sqlite3PutVarint(output + offset, value)`, never `value | 1`, `value + value`, `offset + output`, `p + 1` or a cast. A narrowed input belongs in SETUP, where the reviewer checks it. A card function is never named except as such a call (no function pointers to it, no helper that calls it).
  - SETUP holds only declarations, `__CPROVER_assume` of sizes, pointers and fields of local variables (calling no function but CPROVER primitives such as `__CPROVER_r_ok`), allocations (`p = malloc(n)`, `p = (T *)malloc(n)`), and assignments that read and write no data bytes (no subscripts, no `*p`). Also not in SETUP: `&` (taking an address), `->` except as `p->field = value`, string literals, casts to a pointer type except on malloc, and naming a local array outside `sizeof`. A data pointer holds only a malloc result, pointer arithmetic on one (`q = p + k`), or 0. To bound a field, assume on a local and assign it: `__CPROVER_assume(n < 4); m->n = n;`.
  - Anywhere in a harness: no preprocessor directive but `#include` (so no `#define` or `#undef`), no loop or function contract clauses (`__CPROVER_loop_invariant`, `__CPROVER_decreases`, `__CPROVER_assigns`, `PROOF(...)`, ...), no `__builtin_*` but the bit and byte-order ones scan.py lists (never `__builtin_unreachable` or `__builtin_assume`), no `__attribute__` or `asm`, and no line splices, digraphs or trigraphs.
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

Contracts are clauses on a separate declaration, `contract_<fn>`, with the function's own signature. `--enforce-contract fn/contract_fn` checks `fn` against it, and `--replace-call-with-contract fn/contract_fn` uses it at call sites; both work on static functions. SQLite's text gets only loop annotations. A boundary contract (one for a function no card proves) names its ledger entry in a comment, `Ledger: A-NNN`, and is that entry's clause word for word (scan.py compares them, comments and spacing aside). The three in milestone 1, sqlite3DbMallocRaw.h, vdbeCompareMemString.h and sqlite3CorruptError.h, were written at checkpoint 1 and are frozen; builders replace calls with them and do not edit them.

**Bodies removed.** Before drop-unused-functions, tools/prove.py removes the body of every REPLACE function and of every callee on the card's "Unreached callees, bodies removed" line (checkpoint 1, fix 1). Otherwise drop-unused keeps what those bodies reach, and for sqlite3VdbeMemSetNull that includes os_unix's syscall table, on which DFCC aborts. A call that a proof does reach to an unreached callee fails it: under DFCC as "undefined function should be unreachable", otherwise as a function without a body.

**Statics and globals.** Under DFCC (a proof with ENFORCE, REPLACE or a loop contract), every static and global, SQLite's included, starts unconstrained: SQLite's initializers (such as `sqlite3PendingByte = 0x40000000`) are not assumed. That over-approximates SQLite's initialized globals. A proof without contracts (COVER only) keeps every initializer, and a static local starts at zero. So an input is always a plain local of the entry function, never a static or a global.

Shared headers (contracts, `proofs/include/preds.h`, `proofs/spec/`) #define nothing but an include guard and #undef nothing: `#ifndef G` as the first code and `#define G` on the next line, G an all-caps name ending in `_H` that sqlite3.c doesn't use, or `#pragma once` instead. Write a predicate as a static function, never a macro: scan.py rejects any other macro, because one could change an existing predicate's meaning while every line preds.h held stays in place.

## Loop contracts: PROOF spans in `overlay/sqlite3.c`

`PROOF(__CPROVER_assigns(...) __CPROVER_loop_invariant(...) __CPROVER_decreases(...))`, in that order. Put every character of the span, whitespace included, inside the parentheses: `tools/check_overlay.py` deletes exactly `PROOF(` to its matching `)` and requires upstream to remain.
- **for and while loops:** between the condition's `)` and the body, e.g. `while( i<n )PROOF(...){`.
- **do-while loops:** between `do` and the body: `do PROOF(...){ ... }while( c );`. In CBMC 6.11, clauses after a do-while's condition do not parse (GOAL.md §1.3 and builder §2.6 now say so). A do-while invariant is checked before the first iteration, so it must hold at the top of every iteration.
- A loop bounded by construction at 16 iterations or fewer may be unwound instead (`<p>_LOOPS := unwind` and `<p>_UNWINDSET`).

## Bounded proofs

Only Zach makes a proof bounded, through tools/prove.py's `BOUNDS`, a frozen file (evidence/approvals/C-15-bounded/ and T-015-followup/). A bounded proof proves its property only within the bounds given there, and tests the functions past them natively. scan.py rule 16 checks the mechanics:
- **Any other constant upper bound on an input fails scan, in every proof.** An input is a local passed whole to the call under proof (`id`, `&id`, or `x` in `x + y`), a value assigned to a field of an input object, a local an input is assigned from, or a pointer that aliases an input. Examples are `__CPROVER_assume(n <= 64)`, `!(n > 64)` and `n == 4`. Lower bounds such as `n >= 0` are fine. So are bounds on an allocation's size or a pointer's offset in an unbounded proof (C-01's `extent <= 16`): the reviewer judges whether those narrow anything.
- **In a bounded proof:**
  - SETUP holds each of its bounds as exactly `__CPROVER_assume(<local> <= K);`, once.
  - An allocation's size counts as an input, so it can't carry a constant bound.
  - It allocates only single objects (`sizeof(T)`) and the constant-size buffers BOUNDS names, each as large as the largest extent its bounds allow. A buffer is used only as `<buffer> + <offset>`, then only the tail terms BOUNDS names. Its offset is set once, in one of two shapes, each its own proof: 0 (start-exact, so an underread fails), or `(<size>) - (<extent>)` (end-exact, so an overread fails), where `<extent>` is the exact extent the contract requires.
  - Or it allocates exactly at a symbolic size, `malloc(<local>)` or `malloc(sizeof(T) * <local>)`, the local an input that only BOUNDS bounds or fixes (C-17). That is better than the two shapes, which C-15 needed only because exact symbolic sizes ran it out of memory.
  - BOUNDS may fix an input instead of bounding it, as C-17's one proof per (bSkip, nField) does. SETUP then holds exactly `<local> = <value>;` once. In every proof, a constant value given to an input is refused unless BOUNDS fixes it.
- **The label:** `<card> <proof>: bounded: <what> <= K, ...` appears word for word in the card and in PROPERTIES.md, and RESULTS.md prints it in its Bounds column. A card whose BOUNDS has a `_label` carries `<card>: <label>` instead, once. A `*` entry binds every proof of the card, as for C-18 to C-20, which carry C-17's bound through its contract.
- **An excepted failure:** C-17's every bounded proof fails F-001's overflow at 92793, which tools/prove.py's EXCEPTED_FAILURES excepts, strictly. Any other failure fails the proof. So does a configuration in which the excepted failure doesn't occur. Mutants count as killed only by another failure. The card and RESULTS.md say "proved except F-001 at 92793".
- **Legacy loops unwound:** with `<name>_CONTRACTS := legacy` and `<name>_LOOPS := unwind`, prove.py unwinds the loops with `--unwinding-assertions` before enforcement (legacy-unwind), and needs an UNWINDSET.
- **SETUP's one subscripted store:** `p->aColl[k] = c`, a KeyInfo's collation pointer. k is a local, and c is a local set exactly once to `malloc(sizeof(CollSeq))` and stored nowhere else. Not `0`: that would fix the entry as NULL, while `--malloc-may-fail` already gives NULL or a valid CollSeq.
- **Native tests past the bound:** `tests/bounded/<card>-<k>.c` (k 1 to 9) `#include "sqlite3.c"` from unmodified upstream and test the card's functions past the bounds. tools/native.py builds and runs them with campaign.py's repro command (ASan and UBSan) in its sandbox, as a step of every gate that runs the card. A test passes if it exits 0 with no sanitizer report. Sessions don't run the gate, and inside one the sandbox can't start. Compile and run a test yourself to develop it.

## Running

- `tools/prove.py prove --card-dir proofs/C-NN [--config lp64-le|ilp32-le|lp64-be]`, `tools/prove.py coverage --card-dir proofs/C-NN [--config ...]`, `tools/mutate.py --card C-NN`, `tools/check_overlay.py`, `tools/scan.py --card C-NN --base main`. Without `--config` they run every configuration.
- **Never `make -C proofs/C-NN`, in any session** (checkpoint 1, fix 2). make evaluates the card's Makefile, so a builder's line such as `PY := <cmd>; python3` would run `<cmd>` in whoever's session runs make, before scan or prove.py could reject it. tools/prove.py reads the Makefile with its own declarative parser and never runs it; the gate does the same.
- **Long runs under Codex (builders):** wait once, never poll (builder §2.9). In one exec cell:
  ~~~
  const r = await tools.exec_command({cmd: "tools/prove.py prove --card-dir proofs/C-NN --config lp64-le > $TMPDIR/C-NN.log 2>&1; tail -5 $TMPDIR/C-NN.log", yield_time_ms: 1000});
  // if r is still running (it has a session_id and no exit code):
  text(await tools.write_stdin({session_id: <its session_id>, chars: "", yield_time_ms: 3600000}));
  ~~~
  sessions.toml sets `background_terminal_max_timeout` and `features.code_mode.default_exec_yield_time_ms` to an hour, so that call, and the cell around it, return when the command exits. A 15-minute command cost 36,925 tokens this way and 748,078 polled once a minute (evidence/bringup/13-checkpoint0.md). Background jobs don't work: the sandbox kills a command's background children when it returns, even `setsid nohup … &` (evidence/bringup/10-cli.md).
- **Long runs under Claude (reviewers):** background with output in a file, or a long timeout. The reviewer's /tmp is private to its session.
- Each ends with a `RESULT` line. Sessions have `GNUMAKEFLAGS=--no-print-directory` set, so that line is last. Without it, make adds "Leaving directory" after it.
- Building the overlay with goto-cc takes about 6 s per configuration. A proof's CBMC time is separate, and each CBMC run has a 600 s timeout.
- A proof also fails if CBMC reports a function without a body: calls to it would be unconstrained. Replace such a callee with a contract, or let its body run.
- A proof also fails if, in an entry function, an argument of a call to a card function (macros such as `getVarint32` included) does not have the parameter's type before any cast, checked on the linked goto program. `u32 value` passed for a `u64` parameter covers only part of its range, and scan cannot see types: declare each input with exactly the parameter's type (`u64 value`, `unsigned char *output`). In `p + k`, k must be `size_t`. A cast to the type the operand already has is fine. The entry function must call its ENFORCE function directly (a proof without ENFORCE: some card function), so the check always has a call to look at.
- CBMC's malloc may return NULL (`--malloc-may-fail --malloc-fail-null`). Put the NULL check in SETUP: `__CPROVER_assume(p != 0)`.
- Mutants live in `proofs/MUTANTS`; `card=` says which card's proofs must kill each one.
