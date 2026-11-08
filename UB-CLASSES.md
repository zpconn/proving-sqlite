# UB-CLASSES

The kinds of undefined behavior in C11 Annex J.2 that can arise in the 22 functions of GOAL.md Appendix A, each with how milestone 1 handles it:
- **checked:** by a CBMC option in `proofs/CHECKS`, named here. Each was shown to fire on a toy: `evidence/bringup/toys/04-checks/` (`run.sh`, `result.txt`, `more_ub_result.txt`).
- **argued:** by inspection, with the sites listed. These are not *proved*, and every card's reviewer re-checks the sites in that card's functions.
- **out of scope:** with the reason.

This is the bring-up version (GOAL.md §1.4). §2.6 confirms the sites against each function and the call graph. Line numbers are upstream/sqlite3.c.

## Checked

| J.2 class (C11 clause) | Option | Toy |
|---|---|---|
| Array subscript out of range; pointer arithmetic result used with `*` outside its array (6.5.6) | `--bounds-check`, `--pointer-check` | BOUNDS, POINTER |
| Pointer arithmetic producing a result outside the array or one past it (6.5.6p8) | `--pointer-overflow-check` | POINTER_OVERFLOW |
| `*` applied to a null, invalid or dead pointer; an object referred to outside its lifetime (6.5.3.2p4, 6.2.4p2) | `--pointer-check` | POINTER (dead object), MALLOC_MAY_FAIL (NULL) |
| A pointer to freed space is used (7.22.3p1) | `--pointer-check`, `--pointer-primitive-check` | POINTER_PRIMITIVE |
| Signed integer overflow, including `+ - * ` and unary minus (6.5p5) | `--signed-overflow-check` | SIGNED_OVERFLOW |
| Left shift of a signed value whose result is not representable (6.5.7p4) | `--signed-overflow-check` | SHL_OVERFLOW |
| Shift by a negative amount or by ≥ the width; left shift of a negative value (6.5.7p3–4) | `--undefined-shift-check` | UNDEFINED_SHIFT, NEG_SHIFT |
| Second operand of `/` or `%` is zero (6.5.5p5), integer and floating | `--div-by-zero-check`, `--float-div-by-zero-check` | DIV_BY_ZERO, FLOAT_DIV_BY_ZERO |
| Floating value converted to an integer type that cannot represent its integral part (6.3.1.4p1) | `%float-to-int` in CHECKS: a second CBMC pass with `--conversion-check`, restricted to "float to … integer type conversion" properties | FLOAT_TO_INT |
| Relational comparison or subtraction of pointers into different objects (6.5.8p5, 6.5.6p9) | `--pointer-check` ("same object violation") | PTR_RELATION, PTR_SUBTRACT |
| `memcpy` with overlapping objects (7.24.2.1p2) | CBMC's `memcpy` model, under `--pointer-check` | MEMCPY_OVERLAP |
| A library function given an array argument it cannot access in full (7.1.4p1) | CBMC's `memcpy`/`memcmp` models, under `--pointer-check` | MEMCPY_OOB |
| `free` of a pointer not from an allocator, or freed twice (7.22.3.3p2) | CBMC's `free` model | FREE_INVALID, DOUBLE_FREE |
| Allocation failure not handled (malloc returns NULL) | `--malloc-may-fail --malloc-fail-null` | MALLOC_MAY_FAIL |
| A loop bound is too small for the proof to be complete | `--unwinding-assertions` (not UB itself, but a gap in the proof) | UNWINDING |

**Not in CHECKS, and why.** `--conversion-check` runs only through `%float-to-int`, because unrestricted it flags conversions C11 defines (signed to unsigned, 6.3.1.3p2) and narrowing to a signed type, which is implementation-defined (6.3.1.3p3) rather than UB. `--unsigned-overflow-check` is left out because unsigned arithmetic wraps by definition (6.2.5p9). `--nan-check` and `--float-overflow-check` are left out because NaN and infinite results are not UB under IEC 60559 (Annex F), which the configurations follow. `--memory-leak-check` is left out because a leak is not UB.

## Argued

| J.2 class (C11 clause) | Why it cannot arise, and the sites |
|---|---|
| An object's stored value accessed through an lvalue of a type the effective-type rules do not allow (6.5p7) | serialGet (91945) reads `u64 x` through `*(i64*)&x` at 91956. i64 is the signed type corresponding to x's effective type, which 6.5p7 allows. sqlite3GetVarint (38021) reads bytes as `((signed char*)p)[k]` at 38024 and 38028; character types may access any object. The double is filled with `memcpy` (serialGet 91976, serialGet7 91989), not a cast. Reading a union member other than the one last stored (Mem's `u`) is not UB in C11 (6.5.2.3 footnote 95). |
| A trap representation read through a non-character lvalue (6.2.6.1p5) | The configurations use IEC 60559 doubles, and every bit pattern of a 64-bit double is a value, so serialGet and serialGet7's memcpy into `pMem->u.r` cannot create one; a NaN becomes MEM_Null. The integer types have no trap representations on these configurations. |
| The value of an automatic object used while indeterminate (6.2.4p6, 6.3.2.1p2) | CBMC treats uninitialized objects as nondeterministic, so every value they could hold is explored, but it does not flag the read itself. Sites: putVarint64 (37967) reads `buf[0..n-1]` only after writing them (37981–37987). RecordUnpack's corrupt-record case (comment at 92150–92153) reads bytes past the record, which are heap bytes read as `unsigned char`; A-001 makes them readable, and `unsigned char` has no trap representations. Each card's reviewer checks that its function reads no automatic variable before writing it. `gcc -Wuninitialized` reports nothing in sqlite3.c. |
| A non-void function reaches its closing `}` and the caller uses the value (6.9.1p12) | CBMC does not check this (toy NO_RETURN passes). Every function in Appendix A returns on every path: `gcc -O0 -Wreturn-type -c upstream/sqlite3.c` reports nothing. Each card's reviewer confirms it for that card's functions. |
| A pointer converted to a type it is not aligned for (6.3.2.3p7) | CBMC does not model alignment. Sites: sqlite3VdbeAllocUnpackedRecord (92096) converts `&((char*)p)[ROUND8P(sizeof(UnpackedRecord))]` to `Mem*` at 92105. That is aligned if sqlite3DbMallocRaw returns 8-byte-aligned memory, which its ledger contract must state (§2.3). sqlite3GetVarint's `(signed char*)p` and the record decoders' `const unsigned char*` need alignment 1. sqlite3VdbeRecordUnpack asserts `EIGHT_BYTE_ALIGNMENT(pMem)` (92130); that assert is compiled out, so the alignment of `p->aMem` is a requires of C-15, justified by C-14's ensures. |
| An attempt to modify a const-qualified object, or a string literal (6.7.3p6, 6.4.5p7) | No function in scope writes through a pointer derived from its `const` parameters (record bytes `pKey`, `buf`). Each enforced contract's assigns clause, which CBMC checks, lists everything a function writes. |
| A function called through a pointer of incompatible type (6.5.2.2p9) | sqlite3VdbeFindCompare (93010) returns `vdbeRecordCompareInt`, `vdbeRecordCompareString` or `sqlite3VdbeRecordCompare`, all of type RecordCompare. The collation call `pColl->xCmp` is inside vdbeCompareMemString, a boundary contract (LEDGER.md). |

## Out of scope

| Class | Reason |
|---|---|
| Data races (5.1.2.4p25) | The proofs assume single-threaded use, as GOAL.md §6 settles. SQLite's default build is threadsafe, but proving race freedom is a different kind of proof. |
| Stack exhaustion | C11 sets no limit; it is a property of the implementation and the caller's stack. No function in scope recurses. |
| UB inside the boundary callees' bodies (sqlite3DbMallocRaw, vdbeCompareMemString, sqlite3CorruptError) | They are replaced by contracts that are *assumed* (LEDGER.md) and not proved in milestone 1. |
| UB in the C library and in CBMC's models of it | *Trusted* (TRUSTED.md). |
| Code that `#if`/`#ifdef` removes under the default compile options, including SQLite's `assert()` (NDEBUG is defined when SQLITE_DEBUG is not, 15192) | Milestone 1 proves the default build (GOAL.md §6). |
