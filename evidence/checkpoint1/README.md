# Checkpoint 1 (GOAL.md §2)

What §2 asks for, with each item's file. proof.lock is not written, and §3 has not started.

| Item | File | Summary |
|---|---|---|
| Properties | PROPERTIES.md | P1–P3, changed from GOAL.md only where bring-up showed it wrong, each change listed. P3's departures: D1 (NaN is NULL), D2 (types 10 and 11 read 0 bytes, though the table gives "variable"; 10 is NULL with MEM_Zero, 11 is NULL) and D3 (t ≥ 12 reads nothing; MEM_Ephem). |
| 1. Appendix A confirmed against the pin, callees and card order | evidence/checkpoint1/01-scope.md (callgraph.txt beside it) | Every line names its function. Loops match (7). The call graph is identical on the three configurations. It adds memcpy, and vdbeMemClearExternAndSetNull (excluded by C-13's requires). Card order in five waves. |
| 2. proofs/spec/record_format.h, reviewed on the other vendor | proofs/spec/record_format.h; reviews/spec-r1.md; evidence/spec/ | Written from the file format's serial type table (evidence/spec/fileformat2.html, at the pin): 57 lines, each case citing its row. Codex spec review J0011: APPROVE, no issues. Native test against sqlite3VdbeSerialGet: 2,000,000 checks, 0 mismatches (tested, not proved). |
| 3. LEDGER.md drafts | LEDGER.md | A-001 record slack (S to be fixed by C-15, the smallest that works); A-002 sqlite3DbMallocRaw; A-003 vdbeCompareMemString; A-004 sqlite3CorruptError; A-005 nine-byte varint output (C-01's proposal). The boundary clauses were checked in CBMC: evidence/checkpoint1/ledger-clauses/clauses.c. |
| 4. proofs/MUTANTS | proofs/MUTANTS | 62 mutants (M-017 to M-062 new), at least two per function, each with card=. All apply exactly once and compile. None is expected to be equivalent; four kills need a contract clause their card asks for. C-09's five are killed natively (evidence/spec/README.md). |
| 5. A card for every function | cards/C-01.md … cards/C-20.md | Appendix B's caps and tiers. Depends on lines come from the call graph. Every May change line names exact files: reports b1–b6, repro files 1–3, no globs. |
| 6. TRUSTED.md and UB-CLASSES.md | TRUSTED.md; UB-CLASSES.md | UB-CLASSES adds unsequenced side effects (C11 6.5p2: gcc and clang report none; 26 statements checked) and 6.5p7 sites in vdbeRecordDecodeInt and vdbeRecordCompareInt. |
| Caps | evidence/checkpoint1/02-caps.md | The measured waiting cost (one model call, about 35k–50k tokens, per long run) makes no Appendix B cap too tight. No new caps are proposed; C-18 is one to watch. |
| Checks | evidence/bringup/13-tool-tests.txt; evidence/bringup/13-selftest.txt; evidence/checkpoint1/03-full-gate.log | Tool tests 195/195, selftest 86/86. Full gate: `RESULT gate all PASS 6865s 0 failed`; mutants 22/62 killed, 0 equivalent, 40 pending (cards with no proofs yet). C-02's roundtrip already kills M-017 to M-022 (C-03, C-04, C-05). |
| Orchestrator tokens | evidence/orchestrator/tokens.csv | This session, recorded at checkpoint 1. |
