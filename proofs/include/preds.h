/* proofs/include/preds.h: shared predicates for contracts and loop invariants.
** Builders add a predicate here only when none says what they need. Every predicate may state sizes, allocation,
** aliasing and struct field values; none may constrain data bytes (record or page bytes, or the string and blob
** contents a Mem points at). tools/scan.py rejects assumes, pragmas, zero-filling and definitions of names SQLite
** uses; the reviewer checks the rest. Include it after "sqlite3.c". */
#ifndef PREDS_H
#define PREDS_H
#endif
