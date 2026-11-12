/* proof.h: the PROOF(...) macro used to annotate overlay/sqlite3.c.
** Under CBMC the span's contents (contract clauses) are kept; check_overlay.py
** deletes every PROOF(...) span and requires the rest to equal upstream. */
#ifndef PROOF_H
#define PROOF_H
#define PROOF(...) __VA_ARGS__
#endif
