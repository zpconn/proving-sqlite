# PROGRESS

## Status (2026-11-10, campaign session: §3 running)

**In progress:** §3. The campaign started 2026-11-10 15:26 with all 20 cards named (HANDOFF.md, known issue 1). HANDOFF.md's checks passed first: `make gate CARD=C-02` PASS 427s, lock included; selftest 102/102; status as HANDOFF.md says. The card-by-card record is `tools/campaign.py status` and CAMPAIGN.md. **Next:** triage as it comes; §4 (ledger agent) when the boundary contracts and A-001 settle; then §5. Tcl's development files (tcl8.6-dev) are already installed for §4.


**Open questions for Zach:**
1. **T-004, campaign.py's finish kills any tmux session named campaign** (evidence/approvals/T-004-finish-tmux/; approved in principle, unapplied). It waits for the auditor's OK on patch.diff. Until then the selftest runs only under `env -u TMUX TMUX_TMPDIR=<scratch>`.

Answered on 2026-11-10: C-11 (option 1 with the contract addition; the land including results.py's Argued column) and T-003 (the TRUSTED.md entry plus the exact-allocation condition). Tool issues are logged in evidence/orchestrator/tool-issues.md (T-001 to T-004).

The checkpoint 1 list, with each item's file and each fix's test: evidence/checkpoint1/README.md.

- **D1** mutant kills count only from the mutant's own card; pending only while its card has no proofs here or on main; `make gate CARD=C-NN` needs C-NN's own kills; plain `make gate` (§5) fails on any pending mutant, and `ALLOW_PENDING=1` is for mid-campaign full gates.
- **D2** the three boundary headers are written, checked against LEDGER.md by scan.py, and frozen in proof.lock.
- **D4** campaign.py never starts builder round 7; the card goes to triage.
- **Q2/Q4** both CLIs now run in bubblewrap with $HOME and /mnt hidden and read-only. What each loaded before, and what they load now, is in evidence/checkpoint1/07-cli-startup/README.md. Two findings beyond the question:
  - builders loaded Zach's codex approval allow-list (94 rules, `git push` among them);
  - reviewers had the claude.ai "Claude Docs" connector and 32 skills.
  Resume works in real sessions of both.
- **Q5** A-001 is now exact: sqlite3VdbeRecordUnpack reads at most max(nKey, 1) + 8 bytes, whatever nField is.
- **Fixes 1–7:**
  1. DFCC body removal: all 22 functions run on 3 configurations; 71447f2 aborts on 7.
  2. No make in card directories; campaign.py builds and runs repro files, sandboxed.
  3. D4 departure (types 8 and 9).
  4. A-003's omissions stated.
  5. Depends on reasons, checked by scan.py.
  6. Three mutants.
  7. The 6.3.1.4p2 row.

**Checks** (evidence/checkpoint1/): tool tests 228/228 (08-tool-tests.txt); the same test file against 71447f2's tools 193/228, with all 35 failures among the 36 new tests and the 36th a positive control (08-new-tests-at-71447f2.txt); selftest 102/102 (09-selftest.txt); `make gate ALLOW_PENDING=1`: `RESULT gate all PASS 639s 0 failed`, mutants 16/65 killed by their own cards, 0 equivalent, 49 pending and not run (10-full-gate.log); plain `make gate`, the §5 form: `RESULT gate all FAIL 518s failed: mutants all` on those 49 (11-full-gate-strict.log).

**Decisions made at these fixes, approved by Zach on 2026-11-10 with checkpoint 1:**
1. Codex builders now also run inside bubblewrap, not only Claude reviewers. Q2 asked to hide what sessions don't need, and for codex that is only possible from outside: ~/.codex must stay visible for its login and resume. Codex's own workspace-write sandbox runs nested inside, and works (real session).
2. Pending mutants are not run. No result from another card could count, so running them only cost time (the 71447f2 gate spent most of its 6865 s on them).
3. A codex start is refused while ~/.codex/AGENTS.md, AGENTS.override.md, hooks.json, agents/ or /etc/codex exists. None does today.
4. record_format.h changed after its Codex review, in two comments only (D4): accepted without re-review.

**Open questions:** none from these fixes. Q1 (keep 3.53.4) and Q3 (nothing) are settled.

## What bring-up showed GOAL.md or the plan got wrong

1. **Appendix A line numbers** are one past the line naming each function, for all of them. sqlite3CorruptError is at 191373, not 191392. The macros are at 22361–22369 and 91930–91934. Cards cite the naming line (01-lines.txt).
2. **do-while loop contracts** (§1.3, builder §2.6): clauses after the condition don't parse in CBMC 6.11. They go between `do` and the body, and the invariant must hold at the top of each iteration. scan.py enforces this, and proofs/HOWTO.md says it.
3. **Long runs under Codex** (builder §2.9, reviewer §1.5): Codex's sandbox kills a command's background children, even `setsid nohup`, when the command returns. Builders must run long commands in the foreground. The builder prompt and HOWTO say so; Claude reviewers can still background.
4. **Float-to-integer check** (§1.4): CBMC has no such option alone. `--conversion-check` also flags defined and implementation-defined casts, so CHECKS runs it as a restricted second pass.
5. **Configurations** (§1.5): goto-cc's `-m64` silently resets the architecture to x86_64 little-endian, so lp64-be must not pass it. ilp32-le needs gcc-multilib, which Appendix 6 doesn't list (Zach installed it today). Without `--slice-global-inits`, lp64-be runs out of CBMC object IDs.
6. **RESULT last** (§1.9): `make -C` prints "Leaving directory" after it unless `GNUMAKEFLAGS=--no-print-directory` is set; campaign.py sets it for every session and gate.
7. **Claude sessions** (§0.10, §1.10): they run in `--permission-mode auto` inside bubblewrap. This session's auto-mode classifier refused a test launch with bypassPermissions.
8. **Mutants:** each line carries `card=` (the card whose proofs must kill it), so a P1 card's gate never depends on a P2/P3 card that merges later. Since the checkpoint 1 fixes (D1), only that card's proofs count.
9. **P3, types 10 and 11** (§2): GOAL.md takes k from the file format table for t ≤ 11, but the table gives "variable" for 10 and 11. The code reads 0 bytes; PROPERTIES.md states this as departure D2.
10. **Appendix A's callees** (§2.1): the call graph adds memcpy (serialGet, serialGet7, sqlite3IsNaN) and vdbeMemClearExternAndSetNull (sqlite3VdbeMemSetNull's dynamic branch, excluded by its requires).
11. **UB-CLASSES' 6.5p7 sites:** bring-up listed only serialGet; vdbeRecordDecodeInt (92569, 92579) and vdbeRecordCompareInt (92877, 92889) make the same accesses.
12. **DFCC and os_unix** (audit, fix 1): drop-unused-functions runs before DFCC, so a replaced callee's body stays and can reach os_unix's syscall table, on which DFCC aborts. prove.py now removes REPLACE bodies and cards' unreached callees first.
13. **A-001's bound** (audit, Q5): checkpoint 1's draft said idx is bounded only by szHdr and the field count. Inside the loop idx < szHdr ≤ d ≤ nKey, so the extent is max(nKey, 1) + 8.
14. **WSL** (Q4): /etc/resolv.conf links into /mnt/wsl, and Claude Code reads Windows policy through /mnt/c (reg.exe, C:\Program Files\ClaudeCode).

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
- 2026-11-10 Checkpoint 1 fixes (auditor's REVIEW-LOG.md 2026-11-10): D1, D2, D4, Q2, Q4 (real sessions, resume of both), Q5, fixes 1–7, each with a test that fails on 71447f2; evidence/checkpoint1/05–10.
- 2026-11-10 Zach approved checkpoint 1 at 8fbb0c8 (decisions 1–4). proof.lock committed (4b851e7, 38 files). HANDOFF.md written. `make gate CARD=C-02`: RESULT gate C-02 PASS 402s 0 failed; selftest 102/102 (evidence/checkpoint1/12-handoff-*). Found: campaign state keeps the pilot's scope, so `start` needs every card in `--cards` (HANDOFF.md, known issue 1). Setup session ends.
- 2026-11-10 15:26 Campaign session (Zach's /goal, in the setup session's conversation): HANDOFF.md checks passed (gate C-02 PASS 427s, selftest 102/102, status matched). `tools/campaign.py start --cards C-01,…,C-20`: status lists all 20; builders J0012–J0015 on C-03, C-05, C-06, C-07.
- 2026-11-10 16:15 Triage C-11 (NEEDS-DECISION): CBMC 6.11 false failure of the float-to-int check at r = −2^63 (92434), confirmed on toys and natively. Approval request with patch in evidence/approvals/C-11-f2i-exact-min/; C-11 parked.
- 2026-11-10 Zach approved C-11 option 1 with the contract addition. Applied: UB-CLASSES.md, TRUSTED.md, PROPERTIES.md change 7, tools/results.py (Argued column; 4 tests fail on main's tools), cards/C-11.md, proof.lock; landed with APPROVED.md. Started evidence/orchestrator/tool-issues.md (T-001 CBMC float-to-int, T-002 LeakSanitizer under ptrace).
- 2026-11-10 Triage C-16 (NEEDS-DECISION): CBMC 6.11 bounds-checks a flexible array element only at its start (T-003; toys and native ASan in evidence/orchestrator/tool-issues/T-003/). Decision in cards C-16 and C-17: whole-entry KeyInfo footprints, minus one entry in CBMC plus minus one byte under ASan, checked by the reviewer. TRUSTED.md entry requested (evidence/approvals/T-003-flexarray-bounds/). C-16 retried.
- 2026-11-10 16:35 The selftest's finish killed the live daemon (T-004); restarted 16:37, nothing lost. Fix written and tested (103/103; the control fails 102/103); approved in principle, waiting for the auditor's OK.
- 2026-11-10 Zach approved the C-11 land as queued, and T-003 with the exact-allocation condition. TRUSTED.md and cards C-16 and C-17 updated, with proof.lock and APPROVED.md. C-11 and C-16 are retried once their lands reach main.
