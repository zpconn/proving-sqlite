# §1.1 Pins (2026-11-08)

- Amalgamation: sqlite-amalgamation-3530400.zip from sqlite.org/2026/. SQLITE_SOURCE_ID in sqlite3.h:151 and sqlite3.c:472 is
  "2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc", equal to GOAL.md's value.
  SHA3-256 of sqlite3.c = 67f423e9...c043a16, equal to the value in sqlite.org/releaselog/3_53_4.html.
- Source release: sqlite-src-3530400.zip; its manifest.uuid = bf7c7f30...459bcc, VERSION = 3.53.4. 1281 files in test/.
- Hashes: pin.txt.
- CBMC 6.11.0 (cbmc-6.11.0); goto-cc, goto-instrument, goto-synthesizer 6.11.0.
  SAT back ends built in: minisat2 (default), cadical, glucose, ipasir. kissat: "unknown solver".
  SMT: --z3 / --smt2 work with z3 4.8.12. --cvc5, --bitwuzla, --cprover-smt2 give VERIFICATION ERROR (solvers not installed).
  CBMC 6 enables some checks by default (a toy x*x reported arithmetic overflow without any flag); proofs/CHECKS still lists every check explicitly.
- Newer SQLite release: 3.54.1 is on sqlite.org/download.html. Pin stays 3.53.4 per §1.1. Zach told at checkpoint 0.

## GOAL.md Appendix A line numbers, checked against the pin
Every function's "Line" in Appendix A is the line after the line that names the function (e.g. sqlite3VarintLen is named at 38215,
Appendix A says 38216; the body's first line is 38216). Consistent +1 for all 21 functions + 2 boundary callees, except:
- sqlite3CorruptError is defined at 191373 (body 191374), not 191392.
- The varint macros are at 22361-22369 (Appendix A says 22362-22370); the serial-value macros at 91930-91934 (says 91931-91935).
Cards cite the line naming each function (the line `grep -n 'name('` gives). Full table: evidence/bringup/01-lines.txt.
