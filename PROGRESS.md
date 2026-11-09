# PROGRESS

## Status (2026-11-09, setup session, checkpoint 1: waiting for Zach's review)

**Done:** §0, §1 (bring-up, pilot: C-01 and C-02 merged), checkpoint 0 and all its follow-ups (evidence/bringup/13-checkpoint0.md), and GOAL.md §2. **Next:** Zach reviews checkpoint 1. Then proof.lock, HANDOFF.md, and the campaign session (§3). proof.lock is not written and §3 is not started.

| §2 item | File | State |
|---|---|---|
| Properties P1–P3 | PROPERTIES.md | P3: departures D1–D3, including types 10/11 read 0 bytes (the table says "variable"); every change from GOAL.md listed |
| 1. Appendix A confirmed | evidence/checkpoint1/01-scope.md, callgraph.txt | lines, loops and callees against the pin; adds memcpy and vdbeMemClearExternAndSetNull; card order |
| 2. P3 reference | proofs/spec/record_format.h | 57 lines, each case citing its row; Codex review APPROVE (reviews/spec-r1.md); native test 2M checks, 0 mismatches (evidence/spec/) |
| 3. Ledger drafts | LEDGER.md | A-001 slack (S fixed by C-15), A-002–A-004 boundary contracts (clauses checked in CBMC), A-005 nine-byte varint output |
| 4. Mutants | proofs/MUTANTS | 62, at least 2 per function; none expected equivalent; 4 kills need a contract the card asks for |
| 5. Cards | cards/C-01.md … C-20.md | Depends on and May change lines; every May change line names exact files |
| 6. Trust and UB | TRUSTED.md, UB-CLASSES.md | UB-CLASSES adds 6.5p2 (unsequenced) and more 6.5p7 sites |
| Caps | evidence/checkpoint1/02-caps.md | waiting cost makes no cap too tight; C-18 worth watching |

Checks at checkpoint 1: tool tests 195/195, selftest 86/86, scan PASS, check_overlay PASS; full gate: `RESULT gate all PASS 6865s 0 failed`; mutants 22/62 killed, 0 equivalent, 40 pending (cards with no proofs yet). C-02's roundtrip already kills M-017 to M-022 (C-03, C-04, C-05) (evidence/checkpoint1/03-full-gate.log).

**Decisions in this checkpoint for Zach** (made in tools or agents/ before the freeze; each can be undone):
1. `mutate.py --all` reports a survivor whose card has no proofs yet as PENDING instead of failing, so the full gate passes during the campaign; at the end nothing is pending. GOAL.md §3.4 still says "every mutant … killed".
2. Builders write boundary-callee headers word for word from LEDGER.md (builder §1); C-14 writes sqlite3DbMallocRaw.h, C-17 writes vdbeCompareMemString.h and sqlite3CorruptError.h.
3. The file format document at the pin is evidence/spec/fileformat2.html, from sqlite-doc-3530400.zip, downloaded from sqlite.org (hashes in evidence/spec/README.md).
4. May change lines list reports b1–b6 and repro files 1–3; a card retried past round 6 needs its line extended.

**Open questions for Zach:**
1. SQLite 3.54.1 is out; the pin stays 3.53.4 per §1.1.
2. Codex's ChatGPT connectors, web search and subagents are disabled for builders; anything else to turn off?
3. Claude's login expires 2026-12-07 22:27 UTC; an expired login pauses the vendor with a triage item.
4. A reviewer can still read the rest of / and reach host sockets with network on. Hide $HOME and /mnt wholesale? (13-checkpoint0.md, follow-up 6)
5. A-001: sqlite3VdbeRecordUnpack's header index is bounded by szHdr and the field count, not by nKey, so the slack may grow with nField (C-15's card asks the builder to report it).

## What bring-up showed GOAL.md or the plan got wrong

1. **Appendix A line numbers** are one past the line naming each function, for all of them. sqlite3CorruptError is at 191373, not 191392. The macros are at 22361–22369 and 91930–91934. Cards cite the naming line (01-lines.txt).
2. **do-while loop contracts** (§1.3, builder §2.6): clauses after the condition don't parse in CBMC 6.11. They go between `do` and the body, and the invariant must hold at the top of each iteration. scan.py enforces this, and proofs/HOWTO.md says it.
3. **Long runs under Codex** (builder §2.9, reviewer §1.5): Codex's sandbox kills a command's background children, even `setsid nohup`, when the command returns. Builders must run long commands in the foreground. The builder prompt and HOWTO say so; Claude reviewers can still background.
4. **Float-to-integer check** (§1.4): CBMC has no such option alone. `--conversion-check` also flags defined and implementation-defined casts, so CHECKS runs it as a restricted second pass.
5. **Configurations** (§1.5): goto-cc's `-m64` silently resets the architecture to x86_64 little-endian, so lp64-be must not pass it. ilp32-le needs gcc-multilib, which Appendix 6 doesn't list (Zach installed it today). Without `--slice-global-inits`, lp64-be runs out of CBMC object IDs.
6. **RESULT last** (§1.9): `make -C` prints "Leaving directory" after it unless `GNUMAKEFLAGS=--no-print-directory` is set; campaign.py sets it for every session and gate.
7. **Claude sessions** (§0.10, §1.10): they run in `--permission-mode auto` inside bubblewrap. This session's auto-mode classifier refused a test launch with bypassPermissions.
8. **Mutants:** each line carries `card=` (the card whose proofs must kill it), so a P1 card's gate never depends on a P2/P3 card that merges later. The full gate still runs every mutant against every proof.
9. **P3, types 10 and 11** (§2): GOAL.md takes k from the file format table for t ≤ 11, but the table gives "variable" for 10 and 11. The code reads 0 bytes; PROPERTIES.md states this as departure D2.
10. **Appendix A's callees** (§2.1): the call graph adds memcpy (serialGet, serialGet7, sqlite3IsNaN) and vdbeMemClearExternAndSetNull (sqlite3VdbeMemSetNull's dynamic branch, excluded by its requires).
11. **UB-CLASSES' 6.5p7 sites:** bring-up listed only serialGet; vdbeRecordDecodeInt (92569, 92579) and vdbeRecordCompareInt (92877, 92889) make the same accesses.

## Notes for §3

- Every commit campaign.py makes carries a Campaign: trailer, its merges of main into card branches and orch included (C8). The pilot's two merges of main (4a793a2, 3d01a2e) predate this and have none.
- results.csv's lp64-be rows predate -funsigned-char; the next merge that reruns each card regenerates them.
- Token counting: codex counts input (which already includes cache reads) + cache writes + output; claude counts input + cache reads + cache writes + output.
- A-005 (C-01's nine-byte output) is numbered; LEDGER.md's entries are all drafts until the cards that use them settle.

## Log

- 2026-11-08 11:50 Installed the instruction files from PLAN.md's appendices; PLAN.md moved to evidence/handover/. Auditor's settings.json already present. Told Zach the auditor can start.
- 11:52 Machine check: everything present. Pins downloaded and verified.
- 12:00–12:30 Toys for §1.2–§1.5. Asked Zach for gcc-multilib; installed 12:30.
- 12:30–13:20 Tools, tests, campaign.py, fake CLIs, selftest; CLI checks with real codex and claude (13:04: found the Codex background-job behavior).
- 13:22 Pilot started. 13:24 killed C-02's builder; resumed. 13:37 C-02 merged. 13:40 C-01 r1 REJECT; r2 approved 13:53; merged 14:03. 14:17 full gate PASS. 14:18 finish.
- 14:20–14:40 Planted-bug check. Fixed three tool issues the pilot exposed (12-pilot.md); tests 52/52, selftest 31/31, `make gate CARD=C-02` PASS on main.
- 14:40 Checkpoint 0 reported. Zach approved corrections 1–8 and gave decisions B–E with the auditor's fixes C1–C10; he renewed the Claude login.
- 15:50–16:20 D: found the two Codex settings that let one tool call block (probes in the scratchpad); found and disabled the connectors. 16:25–16:45 before/after 15-minute wait measured.
- 16:00–17:30 B, C1–C10, E implemented with tests; GOAL.md, agents/, AGENTS.md, HOWTO, 10-cli.md updated; real reviewer sandbox probed; full gate on the changed tree.
- Evening: auditor's re-audit. Follow-up item 1 (gate never evaluates card Makefiles) done with two tests that fail on 1c27db4.
- Follow-up item 3 (coverage explanations) done with six tests that fail on 8822461.
- Follow-up item 4 (no macros in shared headers but the include guard) done with six tests that fail on ae6421e.
- Follow-up items 5–8 (session commands, reviewer sandbox, worktree files, builder TMPDIR) done; the new selftest steps fail on 9dc55a3 (38/66), pass now (78/78); real sandbox check run (48,875 tokens).
- Follow-up item 2 (harness discipline) done with 22 tests that fail on f7544f5; C-02 now fails scan, left for a decision.
- Zach's decision: allow one snapshot form (S[k] = X[k], or that as a constant-bounded ++i loop body; S a local array the call and SETUP never name). C-02 passes as merged; 12 snapshot tests. Full gate at bc6cb37: RESULT gate all PASS 1008s 0 failed.
- Night: auditor's recheck items 1–3 done (card-function arguments in scan rule 11, {model}/{effort} validation, a timeout on the FIFO check), plus a race in the selftest's phase wait; every new test fails on 20ce5b0. Tool tests 159/159, selftest 86/86, scan PASS. Full gate not rerun.
- 2026-11-09: recheck item 1 tightened: in a card-call argument `x + y`, x must be a pointer declared before or in SETUP and y another identifier (`value + value` passed). Four tests that fail on 85bfa82; tool tests 163/163, scan PASS.
- 2026-11-09: recheck item 1 tightened again: every name in a card-call argument is a local the entry function declares before or in SETUP (SQLITE_ROW, an enum constant, sqlite3PendingByte passed). Nine tests that fail on c9dae3a; tool tests 173/173, scan PASS.
- 2026-11-09: entry functions may not declare anything static, extern or thread-local (a COVER-only proof kept a static input at 0). Five tests that fail on 6422661; tool tests 178/178, scan PASS. HOWTO notes DFCC leaves statics and globals unconstrained.
- 2026-11-09: entry-function declarations may name no macro from sqlite3.c, proof.h or an included header (SQLITE_PRIVATE is static, SQLITE_EXTERN extern); system headers' macros come from gcc -dM -E per configuration. Five tests that fail on 7b3a029, one typedef test that passes; tool tests 184/184, scan PASS.
- 2026-11-09: prove.py fails a proof whose entry function passes a card function an argument with a type other than the parameter's (before any cast; k in p + k size_t), checked on the linked goto program. Four tests that fail on f49022f; tool tests 190/190. Full gate at fc90cc0: RESULT gate all PASS 921s 0 failed.
- 2026-11-09 night: the argument-type check fails a proof whose entry makes no direct call to its ENFORCE function (or, without ENFORCE, to any card function). A COVER-only proof with no card call passed before; tool tests 192/192. Full gate not rerun.
- 2026-11-09: Zach approved the checkpoint 0 fixes; GOAL.md §2 carried out. PROPERTIES.md; proofs/spec/record_format.h (Codex spec review J0011, 140,902 tokens: APPROVE); LEDGER.md drafts A-001 to A-005; proofs/MUTANTS to 62; cards C-03 to C-20; TRUSTED.md; UB-CLASSES.md for 6.5p2; Appendix A confirmed (evidence/checkpoint1/). mutate.py --all reports PENDING for cards without proofs. Waiting cost makes no cap too tight.
