# Approval: T-006, CBMC's legacy contracts for C-15 and C-17 (Zach, relaying the auditor, 2026-11-10)

Zach's answer, verbatim:

> T-006: the auditor OKs patch.diff as written. Land it with proof.lock and the approval record, then C-15 round 3 and C-17 round 4.

and, on the planted bug (README, last section):

> Planted bug: agreed, after the land. C-15 doesn't merge until its gate kills M-050 and M-051 with its own proof, a bug planted by hand with mutate.py --adhoc is caught, and its reviewer has checked why sqlite3VdbeSerialGet's body is kept (T-012).

Applied: `patch.diff` exactly as written (the staged change was compared byte for byte), with proof.lock rewritten. Tests on the patch: tool tests 252/252 and selftest 107/107 (`tool-tests.txt`, `selftest.txt`).
