# F-002 draft (ledger agent, 2026-11-10): sqlite3_preupdate_old decodes an unpadded record

- **Draft:** reports/ledger-2026-11-10.md §4; the ledger agent's repro is evidence/ledger/2026-11-10/repro/.
- **`repro.c`:** that repro with two lines changed, so campaign.py's fixed repro command can build it. It defines `SQLITE_ENABLE_PREUPDATE_HOOK` and includes the unmodified upstream sqlite3.c first, which defines `_GNU_SOURCE` before any system header.
- **`campaign-run.txt`:** campaign.py's `run_repros` (tools/campaign.py) built and ran it against main's upstream/sqlite3.c (b1dd5d74…), in its sandbox with no network, no $HOME and an empty environment. Build exit 0, run exit 1: ASan heap-buffer-overflow READ in serialGet 91950, via sqlite3VdbeSerialGet 92064, sqlite3VdbeRecordUnpack 92143, vdbeUnpackRecord 95888 and sqlite3_preupdate_old 95944.
- **`campaign-control.txt`:** the same fixed build and sandbox, run with argument `clean` (no corruption): exit 0, no report.
- **The auditor** reproduced it natively too (Zach, 2026-11-11): gcc -O1 ASan, only `-DSQLITE_ENABLE_PREUPDATE_HOOK`, the same stack, and the control clean.
- **Status:** reproduced. Judged by a one-off Codex session (J0117, reviews/finding-r1.md: APPROVE, 2026-11-11), which rebuilt and reran the repro and its control. It is FINDINGS.md F-002, with tests/repro/F-002.c, which is repro.c.
