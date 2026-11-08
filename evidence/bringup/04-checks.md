# §1.4 Checks (2026-11-08)

`proofs/CHECKS` lists `--bounds-check --pointer-check --pointer-overflow-check --pointer-primitive-check --signed-overflow-check --undefined-shift-check --div-by-zero-check --float-div-by-zero-check --malloc-may-fail --malloc-fail-null --unwinding-assertions`, plus the `%float-to-int` directive. Every option is in `cbmc --help` (CBMC 6.11.0).

Rerun: `toys/04-checks/run.sh`; output `toys/04-checks/result.txt`. Each toy commits one UB. Run with all of CHECKS, it fails on the named check; run with only that option removed (and its `--no-` form where CBMC 6 enables it by default), it passes. That held for all 13 toys: POINTER, BOUNDS, POINTER_OVERFLOW, POINTER_PRIMITIVE, SIGNED_OVERFLOW, UNDEFINED_SHIFT, NEG_SHIFT, SHL_OVERFLOW, DIV_BY_ZERO, FLOAT_DIV_BY_ZERO, MALLOC_MAY_FAIL, UNWINDING and FLOAT_TO_INT.

- **Float-to-integer:** CBMC has no option for it alone. `--conversion-check` catches `(i64)r` out of range, but it also flags `(u64)s` and `(u32)s` for signed s (defined behavior) and `(int)s` (implementation-defined). SQLite does such casts throughout, so CHECKS runs `--conversion-check` only in a second pass, checking only the properties described as "float to … integer type conversion" (`--property`). tools/prove.py implements the pass; the toy shows pass 2 fails and pass 1 alone passes.
- CBMC 6 enables bounds, pointer, signed-overflow, shift, division, pointer-primitive and unwinding-assertion checks by default; CHECKS still names every one, and scan.py rejects any `--no-` option.
- `more_ub.c` (`more_ub_result.txt`): pointer comparison and subtraction across objects, memcpy overlap or out-of-bounds, and invalid or double free are each caught. A non-void function falling off its end is not, so UB-CLASSES.md argues that class.
- `UB-CLASSES.md`: every J.2 class that can arise here, marked checked (by option), argued (with sites) or out of scope.
