# Checkpoint 0 decisions (2026-11-08)

Zach's decisions A–E after checkpoint 0, and the auditor's fixes (its REVIEW-LOG.md, issues 1–10). Each change and the test that covers it. Tool tests: `tools/tests/test_tools.py` (13-tool-tests.txt). Selftest: `tools/campaign.py selftest` (13-selftest.txt). Full gate on the changed tree: 13-full-gate.log.

## A. GOAL.md corrections 1–8, approved

| # | Where | Change |
|---|---|---|
| 1 | GOAL.md intro, Appendix A | Every line is the one naming the function; macros 22361–22369 and 91930–91934; sqlite3CorruptError 191373 (01-lines.txt) |
| 2 | GOAL.md §1.3, builder §2.6, HOWTO | do-while clauses go between `do` and the body; the invariant holds at the top of every iteration |
| 3 | builder §2.9, AGENTS.md §9, HOWTO, campaign.py LONG_RUN_CODEX | Codex builders don't background long runs; they wait once (see D). Claude sessions still may |
| 4 | GOAL.md §1.4 | No float-to-int option alone; CHECKS' restricted `--conversion-check` pass |
| 5 | GOAL.md §1.5 | lp64-be must not pass -m64; ilp32-le needs gcc-multilib (and B) |
| 6 | GOAL.md §1.9 | `GNUMAKEFLAGS=--no-print-directory` keeps RESULT last |
| 7 | GOAL.md §3.1 Sessions | Claude sessions in auto mode inside bubblewrap; campaign.py fixes vendors (and C5, C6) |
| 8 | GOAL.md §2.4 | Mutant lines carry `card=` |

GOAL.md §3.1 and §3.4 also now list C1–C10 and E, since they describe what campaign.py and the gate do.

## B. lp64-be gets -funsigned-char

proofs/CONFIGS adds `-funsigned-char` to lp64-be; scan.py's CONFIGS whitelist allows it, and only it, among char flags. The probe (tools/probe/config_probe.c, prove.py `expectations`) now asserts plain char's signedness under CBMC and under the preprocessor (`__CHAR_UNSIGNED__`): unsigned on lp64-be, signed on the two little-endian configurations. Nine assertions per configuration, all pass. Tests: `probe: lp64-be with -funsigned-char passes`, `probe: lp64-be without -funsigned-char (x86's signed char) fails`, `scan: CONFIGS may carry -funsigned-char but not another char flag`. C-01 and C-02 still pass on lp64-be with it (13-full-gate.log). results.csv's lp64-be rows still come from the pilot's merge gates, run before the flag; the campaign regenerates them at the next merge that reruns each card.

## C. The auditor's fixes

| # | Fix | Where | Tests |
|---|---|---|---|
| 1 | scan rejects abort, exit, _Exit, _exit, quick_exit, longjmp and kin, setjmp, thrd_exit, pthread_exit, `__builtin_trap/unreachable`, `__VERIFIER_*`, `__CPROVER_array_set/replace/copy`, `__CPROVER_havoc_object/slice` (matched as names, so a function pointer is caught) in harnesses, predicates, specs and contracts. In each entry function: no return or goto; exactly one SETUP block; only declarations before it; in it only declarations, assumes of primitives, allocations and assignments that read and write no data byte; the call under proof after END SETUP, as a plain statement (not in an if, loop, `?:`, `&&`, `\|\|`); no SETUP block outside an entry function. Also: no #import, #embed, #line, and no #pragma but once | scan.py rules 10–12 | 21 `scan rejects (C1): …` tests, including the auditor's three demonstrated cases (`if(c) abort();`, `__VERIFIER_assume(c);`, `if(c) return;`), two SETUP blocks, a data byte stored or copied in SETUP, the call under proof inside a condition |
| 2 | scan rejects any file in proofs/C-NN/ but harness.c, Makefile, NOTES.md (and the ignored build/), any file in overlay/ but sqlite3.c or in proofs/include/ but proof.h and preds.h, and any symlink under proofs/, overlay/, tests/repro/. campaign.py stages a builder's changes in a scratch index and refuses (triage, nothing committed) a symlink, a submodule, a mode change or a new file whose mode isn't 100644. The gate's new `includes C-NN` step (`tools/prove.py includes`) preprocesses each harness on every configuration and fails on any file but overlay/sqlite3.c, proofs/{include,contracts,spec}/*.h and system headers | scan.py rule 12; campaign.py `mode_problems`; prove.py `include_problems`; gate.py | `scan rejects (C2)`: shadow header in proofs/C-90/contracts/, symlinked harness.c, extra file in overlay/, symlink under tests/repro/; `includes`: clean passes on 3 configurations, a shadow header fails, a header pulling in upstream/ or proofs/include/contracts/ fails; selftest C-19 (symlink) and C-20 (executable harness.c) |
| 3 | A coverage gap counts as explained only when listed under a `## Unreached lines` heading in NOTES.md | prove.py `explained_lines`; builder §3.4, reviewer checklist 4, HOWTO | `coverage: the gap cited in NOTES.md outside "Unreached lines" (a requires table) is not an explanation`, `… listed under "## Unreached lines" … passes` |
| 4 | scan --base rejects a preds.h that drops or alters any file-scope item it held; with BASE, `make gate CARD=X` adds every card whose preprocessed harness includes preds.h when preds.h differs from BASE | scan.py rule 13; gate.py `preds_users` | `scan (C4): preds.h gaining a predicate passes`, `scan rejects (C4): a predicate in preds.h changed`, `gate: preds.h unchanged … runs C-90 only`, `gate: preds.h changed … also reruns C-91` |
| 5 | campaign.py fixes builder→codex, reviewer→claude, ledger→claude, spec-review→codex (ROLE_VENDOR) and refuses a sessions.toml that disagrees; re-reviews get the vendor check too; `command_problems` refuses a codex command without `sandbox_mode="workspace-write"` and `approval_policy="never"`, each exactly once, or with a flag that loosens them, and a claude command that doesn't start with bwrap (C6's mounts, `claude -p`, auto mode, no bypass) | campaign.py | selftest: 10 `session guard refuses …` steps, `refuses a sessions.toml that puts builders on claude`, `a re-review is refused when its reviewer would share the vendor …`, C-15 |
| 6 | Reviewer bwrap: `--tmpfs /tmp`, `--tmpfs ~/.codex`, `--tmpfs ../proving-sqlite-wt` (state/, main/, merge/, other worktrees), `--tmpfs <primary>` with its .git ro-bound back; own worktree, ~/.claude and ~/.claude.json writable. 10-cli.md says ~/.claude stays writable | sessions.toml; campaign.py fills `{wtroot}`, `{repo}` and creates missing tmpfs mount points | selftest: `a reviewer's sandbox hides …` (a fake reviewer probes each path); real Sonnet session: cli/sandbox_results.json |
| 7 | lock.py check fails when proof.lock is missing and HEAD's history has a commit touching proof.lock, or HANDOFF.md exists; a repo with no commits is pre-freeze; if git can't tell, it fails | lock.py `after_freeze` | `lock (C7)`: pre-freeze passes; deleted after the freeze commit fails; still fails once the deletion is committed; HANDOFF.md without proof.lock fails |
| 8 | Merges of main into card branches and into orch (land, finish) carry a `Campaign:` trailer | campaign.py | selftest: `every commit campaign.py made on any branch carries a Campaign: trailer, its merges of main into card branches (1) and orch (1) included` |
| 9 | Regression tests for callers_of and collect_results. evidence/results/C-NN.json gains `provenance.<field> = {commit, gate_log, gate}`, set by collect_results for each field it rewrites; results.csv gains prove_from, coverage_from, mutants_from and RESULTS.md lists them per card. C-01.json and C-02.json were backfilled from git history: C-01's fields and C-02's proofs and coverage from 5219e56 (C-01 r2's merge, evidence/gate/C-01-r2.log), C-02's mutants from affc94a (C-02 r1's merge, evidence/gate/C-02-r1.log), each marked as backfilled | campaign.py `collect_results`, results.py | `cards.callers_of: two cards sharing functions name each other, never themselves`, `collect_results: a caller's gate (no mutants.json) keeps the card's mutant results, and each field records its own commit and gate log` |
| 10 | scan rejects a card whose functions aren't all in some proof's COVER | scan.py rule 14 | `scan rejects (C10): a card function no proof's COVER names` |

The pilot's merged proofs pass every new rule unchanged: scan, includes, coverage and the full gate (13-full-gate.log).

## D. Waiting under Codex

Codex 0.166 runs a model's tool calls inside a JavaScript exec cell. The cell yields back to the model after 30 s, and `write_stdin` empty polls are capped at 300 s, so a builder told to "let it finish" polls about once a minute. Two settings remove both limits: `background_terminal_max_timeout=3600000` lets a single `write_stdin` call block until the command exits, up to an hour (a 400 s command returned in one call, at 397 s), and `features.code_mode.default_exec_yield_time_ms=3600000` keeps the cell from yielding. Without the second, the model still polled `wait` every 60 s (probe sessions in the scratchpad). `--strict-config` accepts both keys. So Codex can block without polling, and the hand-off to campaign.py was not built.

Measurement (`cli/wait_check.py`, `cli/wait_results.json`): two builder sessions at once, gpt-6-astra at high effort (the standard builder tier), each told to run `sleep 900; echo LONG-RUN-FINISHED` and write the line to long.txt.

| | Command line | Advice in the prompt | Tool calls | Tokens | Wall | long.txt |
|---|---|---|---|---|---|---|
| before | sessions.toml at d26a1d4 | foreground, let it finish (the checkpoint 0 builder prompt) | 36 | 748,078 | 913 s | LONG-RUN-FINISHED |
| after | sessions.toml now | LONG_RUN_CODEX: one exec cell, exec_command then one write_stdin with yield 3600000 | 2 | 36,925 | 913 s | LONG-RUN-FINISHED |

The bring-up check 4 figure of 1,513,662 tokens was a different session (low effort, a first attempt that backgrounded and failed). Builder §2.9 is rewritten to say how to wait. campaign.py's builder prompt carries the same text (LONG_RUN_CODEX), and so does HOWTO.md. The "run the three configurations in parallel" part of D belonged to the hand-off design, so it was not built; `make prove` still runs them in turn.

## E. Expired login

sessions.toml gains `auth_failure_patterns` per vendor (10-cli.md lists the strings). They are matched like usage limits, against stderr and the CLI's own error events only. On a match, campaign.py:
- pauses the vendor with no end time;
- keeps the session in state `auth`, to resume in the same worktree, without counting an interruption;
- adds a vendor triage item asking Zach to sign in again, which `status` and `wait` show.

`tools/campaign.py resume-vendor <vendor>` runs the vendor's login_check. It refuses while that fails, including a past loginExpiresAt. Once the check passes, it lifts the pause and clears the item. Selftest C-18 covers this: the vendor is paused with a triage item and no codex session starts during the pause; resume-vendor refuses while logged out, then resumes; the card merges with 0 interruptions.

## Also found

- `--ignore-user-config` left the ChatGPT connectors switched on in builder sessions: ~300 `mcp__codex_apps__*` tools (Gmail, Sites deploy), plus web search and subagents. They run in codex's own process, outside the shell sandbox. The pilot's builders never called them. They are now disabled (10-cli.md).
- The selftest fixture moved from /tmp to /var/tmp, and its fake CLIs moved from the fixture's tools/ to its HOME. The reviewer sandbox now hides both /tmp and the primary checkout, as it hides them for real sessions, whose CLIs live outside the repo.

## Follow-up 1 (auditor's re-audit, 2026-11-08 evening): the gate never runs make on a card Makefile

gate.py's prove and coverage steps used to run `make -C proofs/C-NN`, which evaluates the card's Makefile, a file the builder writes. They now call `tools/prove.py prove|coverage --card-dir proofs/C-NN` directly, with the arguments proofs/Makefile.common passes (`--overlay overlay --build-dir proofs/C-NN/build`). A card whose Makefile `prove.load_card` rejects gets a failing `prove C-NN` step, and its includes, prove and coverage steps don't run. campaign.py's run_gate matches that step name, so a land sends the card to triage. `make prove` and `make coverage` at the top level use the same path. Builders can still run `make -C proofs/C-NN prove` inside their own sandbox; only the gate stopped. mutate.py already called prove.py directly.

Tests (tools/tests/test_tools.py, gate section): a card Makefile with a `prove:`/`coverage:` rule after the include, which load_card rejects and which writes a marker file if make runs it.
- `gate: a card Makefile with a rule load_card rejects fails the gate, and make never runs it (no marker)`
- `gate: make prove skips the rejected card Makefile too (no marker)`

Against the tools at 1c27db4 both FAIL, with the marker written (make ran the rule). With the fix both pass. Tool tests 97/97 (13-tool-tests.txt). `make gate CARD=C-02 BASE=HEAD` on the real repo passes with the same numbers as before (14-gate-C-02.log): C-02 1350 properties, C-01 675, coverage 399/399 and 81/81, mutants 11/11; the log has no `make -C`.

## Follow-up 3: coverage explanations must match what the run left uncovered

The auditor showed that one entry, `- sqlite3.c:37900-38099: values the harness bounds`, explained five hidden gaps in a C-01 variant. Ranges of up to 200 lines were accepted, in any number, and nothing checked that a listed line was really unreached.

**Format.** prove.py `unreached_entries` reads the `## Unreached lines` section strictly:
- every non-blank line there is one entry, `- sqlite3.c:<line>: <reason>` or `- sqlite3.c:<a>-<b>: <reason>`, or `- none`;
- a line that is anything else (prose, an entry with no reason, an entry naming two lines or ranges) fails coverage.

**Check against the run.** `check_unreached` compares each entry with the run:
- a single line must be uncovered in some proof and configuration of the run;
- a range must lie within one uncovered block, both ends in it;
- an entry naming a line the run covers, or a line that is no coverage goal, fails coverage;
- only accepted entries explain gaps.

**What a block is.** `cbmc --cover location` reports one goal per instruction, with overlapping line sets: a dead `q = 2; q = q + 1; q = q * 3;` gives goals [44,45], [45,46] and [46]. So a block (`uncovered_regions`, recorded per function as `uncovered_blocks` in coverage-summary.json) is the source-level stretch: a maximal run of uncovered goal lines with no covered goal line between them.

**Tests.** They use a new toy function, toyDead2, with a three-line dead branch.
- Accepted: a range within the dead stretch, with a reason.
- Rejected:
  - a blanket range (the auditor's case);
  - a range one line past the stretch;
  - an entry naming a covered line;
  - an entry with no reason;
  - an entry naming two lines;
  - prose under the heading.

All six rejections pass with the fix and FAIL against the tools at 8822461; the accepted case passes on both. Tool tests 104/104. C-01 and C-02 coverage still pass, 81/81 and 399/399: their NOTES.md have no gaps to list. Builder §3.4, proofs/HOWTO.md and GOAL.md §3.4 state the format.
