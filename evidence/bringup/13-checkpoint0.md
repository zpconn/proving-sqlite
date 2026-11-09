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

## Follow-up 4: shared headers define no macros but their include guard

preds.h may only gain predicates (rule 13), but the check compared file-scope items, so an appended `#define toyPos(x) 1` kept every item preds.h held and passed `scan --base` while changing what toyPos means at every use. Contracts and specs had the same opening: `#define toyLen(n) 1` in a contract rewrote a SQLite call in every harness that includes it.

**Rule 15** (scan.py `check_guard_only`, run on preds.h, every proofs/contracts/*.h and every proofs/spec/*.h):
- the only #define allowed is an include guard: `#ifndef G` as the file's first code, `#define G` with no value on the next line;
- G must be all caps, end in `_H` and not be a name sqlite3.c uses (an empty `#define toyLen` guard would erase a function name at every call);
- no #undef at all; `#pragma once` stays allowed.

**Tests.**
- Accepted: preds.h with only its guard, and the guarded preds.h gaining a predicate, both under `scan --base`.
- Rejected under `scan --base`: a macro redefining an existing predicate; an #undef and redefinition of one; an object-like macro naming a SQLite function.
- Rejected under `scan`: a macro in a contract; a #define in proofs/spec/; an include guard named after a SQLite function.

All six rejections pass with the fix and FAIL against the tools at ae6421e; the accepted cases pass on both. Tool tests 112/112. The repository's scan passes (preds.h has guard PREDS_H; the two contracts have no directives). Builder §1, proofs/HOWTO.md and GOAL.md §3.4 state the rule.

## Follow-ups 5–8: how campaign.py starts and isolates sessions

All in tools/campaign.py and tools/sessions.toml, plus the fake CLIs (tools/fakecli/fake.py). Selftest 78/78 (13-selftest.txt). The selftest's new steps were also run against the committed tools at 9dc55a3: the selftest section and fake CLIs of the fix, with 9dc55a3's campaign.py logic and sessions.toml. They fail there (38/66, 13-selftest-followups-5-8-on-9dc55a3.txt).

**5. Exact command lines.**
- campaign.py's `SESSION_COMMANDS` holds each vendor's start, resume and login_check argv. `template_problems` accepts a sessions.toml command only if it equals that argv token for token; the only parts that vary are the placeholders, which campaign.py fills.
- start_session refuses any other command (SessionRefused: triage), `start` refuses to start the campaign, and login_ok fails.
- command_problems still checks the filled command line as a second line.
- load_sessions hashes the file it parsed, and every session-start journal entry records `sessions_sha256`.
- One new placeholder, `{config}`, for item 6's per-session config directory.
- Consequence: a CLI flag change is now a change to tools/campaign.py, which is frozen at checkpoint 1, not to sessions.toml alone.
- Selftest:
  - refused, and never spawned: a codex command without `--disable apps` (command_problems alone accepts it); a codex command with an extra `-c`; a claude command with a literal `--effort max`;
  - accepted: the shipped commands, with the hash in the session-start entry;
  - in the full run, all 45 session-start entries carry the hash of main's sessions.toml.

**6. Reviewer bubblewrap profile.** New mounts and settings:
- `--tmpfs /run/user`, which covers /run/user/<uid>. This is all of /run/user, not just the uid directory, because the uid would have been one more placeholder.
- `--unsetenv DBUS_SESSION_BUS_ADDRESS` and `--unsetenv XDG_RUNTIME_DIR`.
- `--tmpfs` over ~/.claude, ~/.config/gh, ~/.aws and ~/.docker.
- `--ro-bind /dev/null ~/.claude.json`.
- `--bind {config} {config}` with `--setenv CLAUDE_CONFIG_DIR {config}`.

How the config directory works:
- campaign.py creates `{config}` as state/claude-config/<job>/ (mode 700, under state/, which every session's sandbox hides).
- It seeds the directory with a copy of ~/.claude/.credentials.json, plus a .claude.json holding only oauthAccount, userID and hasCompletedOnboarding.
- A resumed session gets its own directory back, so `claude --resume` finds its transcript.
- When the session ends, `release_claude_config` removes the copy of the login.
- If the session refreshed the login, the new tokens are copied back to ~/.claude/.credentials.json, because a refresh can retire the old ones. They are copied only with the same keys, a later expiry and the same subscription.

Mounting details:
- The tmpfs destinations are resolved with realpath before bwrap runs. ~/.aws here is a symlink to /mnt/c/Users/zpcon/.aws, and bwrap resolves an absolute symlink inside its own new root, where /mnt/c isn't mounted yet, so `--tmpfs ~/.aws` failed.
- A hide of gh, aws or docker that has nothing to hide is dropped, because bwrap cannot mount on an absent path.

command_problems now requires each of these mounts and settings. It allows writable binds only of the worktree and that one config directory, and read-only binds only of /, the primary checkout's .git and /dev/null over ~/.claude.json. Selftest guard cases refuse each one left out, ~/.claude bound writable, and CLAUDE_CONFIG_DIR pointed at ~/.claude.

The fake reviewer's probe checks every hide. Because ~/.claude is now hidden, the fake CLIs keep their counters behind a unix socket the selftest serves, instead of in ~/.claude.

**Real session (cli/sandbox_check.py, cli/sandbox_results.json, cli/sandbox_check.log, job J93193-sandbox-c6).**
- The session was a claude-sonnet-5-5 reviewer, started through campaign.py's start_session and runner. It exited 0 with a `success` result and used 48,875 tokens.
- Inside the sandbox:
  - /run/user/1000 had 0 entries;
  - DBUS_SESSION_BUS_ADDRESS and XDG_RUNTIME_DIR were unset;
  - ~/.claude had 0 entries (the host has 19), and its projects/ was hidden;
  - ~/.claude.json was unreadable;
  - CLAUDE_CONFIG_DIR was state/claude-config/J93193-sandbox-c6, seeded, and `claude auth status` there said `"loggedIn": true`;
  - ~/.config/gh had 0 entries (host 2) and ~/.docker 0 (host 6). ~/.aws is empty on the host too, so that probe shows nothing either way.
- The earlier probes still held: the host /tmp, ~/.codex, state/, other worktrees and the primary checkout were hidden, git diff worked, the worktree was writable and .git was read-only.
- On the host afterwards:
  - the session's write to ~/.claude/sandbox-probe went to its tmpfs, and the real file doesn't exist;
  - the copy of the login was removed;
  - the host login is still valid.

**What a reviewer can still read** (not in the auditor's list; not changed):
- the rest of / read-only, including the rest of ~/.config (e.g. configstore and Chrome-for-testing profiles) and /mnt/c, the whole Windows drive;
- host sockets on paths it can see, e.g. /run/dbus/system_bus_socket and /mnt/wslg/PulseServer.

Network stays on. A tmpfs over $HOME and /mnt, binding back only what Claude Code and git need, would close most of this. That is a larger change to propose separately.

**7. Files in a session's worktree.**
- `write_worktree_usage` opens .campaign with O_DIRECTORY|O_NOFOLLOW from the worktree's fd. It requires an existing usage file to be a regular file with one link, opens it with O_NOFOLLOW|O_NONBLOCK, and checks the open file again before truncating.
- Anything else writes nothing. While a session runs, the session is stopped and the card goes to triage. Before a session starts, it is refused, which also sends the card to triage.
- `read_worktree_file` reads reports and reviews:
  - each directory on the way is opened with O_NOFOLLOW;
  - the file is lstat'ed, then opened with O_NOFOLLOW|O_NONBLOCK and fstat'ed;
  - it must be a regular file of at most 4 MB, otherwise the card goes to triage. A one-off session's commit happens only after its reports and reviews pass this check.
- Before the fix:
  - a symlinked usage made campaign.py overwrite the file it pointed to. Demonstrated directly on 9dc55a3's write_usage_file: the outside file's contents became `tokens_used 5 / cap 10 / percent 50.0`.
  - a FIFO report blocked the daemon in open() while it held the state lock. In the 9dc55a3 run, phase A never settled, C-16 and C-18 stayed in reviewing, and `campaign.py land` timed out after 120 s.
- Selftest:
  - C-25 (usage replaced by a symlink to a file outside the worktree) goes to triage with nothing committed, and the outside file is unchanged;
  - C-26 (report is a FIFO) goes to triage with nothing committed, and the daemon carries on;
  - unit cases: usage as a symlink, usage as a hard link to an outside file, .campaign as a symlink to an outside directory, and a FIFO report, a symlinked report and a review under a symlinked reviews/.

**8. Builder scratch space.**
- Codex commands set `-c sandbox_workspace_write.exclude_slash_tmp=true`. command_problems requires exactly that string and no other sandbox_workspace_write key.
- campaign.py sets TMPDIR to tmp/ in the worktree; .gitignore's `/tmp/` already ignores it. It is created at session start and emptied at the start of each new round, not on a resume.
- Checked with `codex sandbox` (the same Linux sandbox, no model) in a scratch worktree:
  - with the key, /tmp is not writable while $TMPDIR and the worktree are, and Python's tempfile uses $TMPDIR;
  - without the key, /tmp is writable;
  - with it, `make -C proofs/C-01 prove CONFIG=lp64-le` passes with 225 properties, 0 failed: CBMC follows TMPDIR, and no tool in tools/ uses /tmp.
- The builder prompt, builder §1 and §2.9, AGENTS.md and HOWTO now say $TMPDIR instead of /tmp.
- Selftest:
  - guard cases refuse a missing key, `=false`, and another sandbox_workspace_write key;
  - a unit start gives TMPDIR in the worktree;
  - all 29 fake codex sessions in the full run saw TMPDIR = their worktree's tmp/.

## Follow-up 2: harness discipline (scan.py rule 11)

The auditor's option taken for macros: harnesses may use no preprocessor directive but #include, so no #define or #undef, rather than applying the rules to preprocessed text. Function-like SQLite macros in SETUP or before the call already count as calls, and both places refuse calls they don't allow.

**New checks** (scan.py `check_harness_text`, `setup_statement_problem`, `check_entries`):
- **Between END SETUP and the call under proof:** only declarations. This is stricter than the list: plain assignments and calls are refused too, because `value = 0;` or a helper that stores narrows the inputs just as `p[0] = 0;` does.
- **In SETUP:**
  - no unary `&`;
  - `->` only as the target of `p->field = value`, never read;
  - no string literals;
  - no cast to a pointer type except on malloc (`sizeof(T *)` is not a cast);
  - no local array named outside sizeof, since an array name stands for its address;
  - a pointer variable (declared `T *p`) may be assigned only `malloc(...)`, `(T *)malloc(...)`, another such pointer plus or minus an offset, or 0.

  Assumes get the same checks, so a field is bounded through a local: `__CPROVER_assume(n < 4); m->n = n;`.
- **Anywhere in a harness:**
  - no directive but #include;
  - no `__CPROVER_loop_invariant`, `decreases`, `assigns`, `frees`, `loop_entry`, `requires` or `ensures`, and no `PROOF(`;
  - no `__builtin_*` outside a short list (expect, offsetof, clz/ctz/popcount, bswap);
  - no `__attribute__` or `asm`;
  - no backslash-newline, digraph (`<:` is `[`) or trigraph (`??(` is `[`). Each spells a token these rules look for in a way they would miss.

**Tests.**
- 22 rejection cases in tools/tests/test_tools.py, at least one per pattern. They cover:
  - a #define hiding a SETUP store, and an #undef;
  - between END SETUP and the call: a subscript store, a pointer store, an if, a loop, and a helper that stores;
  - in SETUP: `&local`, a `->` read in an assume and in an assignment, a string literal, a cast of an integer to `u8 *`, a pointer set to a local array, and a pointer set to an integer;
  - anywhere: a loop invariant and a PROOF() on a harness loop, __builtin_unreachable and __builtin_assume after the call, `__attribute__((constructor))`, a digraph and a trigraph subscript in a SETUP assume, and a line splice hiding an assume.
- Each must give `RESULT scan FAIL`. All 22 fail against the tools at f7544f5: their scan passed every one.
- One accepted case passes on both: field stores, a cast malloc, pointer arithmetic and `sizeof(u8 *)`.
- Tool tests 135/135.

**Effect on the repository: C-02's merged harness now fails the scan.**
- Its harness_roundtrip copies the encoder's buffer between END SETUP and the call under proof, to check afterwards that the bytes past the encoding are unchanged (P2 "suffix is unchanged"):
  `scan: proofs/C-02/harness.c: line 21: between END SETUP and the call under proof (sqlite3PutVarint), entry function harness_roundtrip may only declare variables (no stores, assignments, calls or control flow): for(i=0; i<9; ++i) before[i] = buffer[i]`
- That copy narrows nothing: it reads the nondet bytes and writes a local array the call never receives. But the rule as written refuses it, and an unchanged-suffix check seems to need some copy taken before the call.
- C-01 passes. `make gate CARD=C-NN` still passes for other cards, because scan then checks only that card's harness. The full gate fails until C-02 changes.
- I did not change the harness (no proof edits by the orchestrator).
- **Two ways forward:**
  - reopen C-02 for a builder round under the new rule;
  - let scan allow one snapshot form: `S[i] = X[i]`, alone or in a counted for loop, where S is a local array that the call statement doesn't name and SETUP never names.

### Decision: one snapshot form (Zach, 2026-11-08)

Option two: scan allows one snapshot form between END SETUP and the call under proof, and C-02 stays as merged.

**The form** (scan.py `SNAPSHOT_ALONE_RX`, `SNAPSHOT_LOOP_RX`, `snapshot_problem`):
- exactly `S[k] = X[k];` with a constant k;
- or `S[i] = X[i]` as the whole body of `for(i = <const>; i < <const>; ++i)`, with no braces.

**Conditions:**
- S is declared once in the entry function as an array of constant size: not a pointer, not static or extern, no initializer.
- For the loop form, i is a plain local declared once in the entry function, and no other snapshot loop uses it. Nothing else in the region can assign it, since only declarations may stand there.
- Neither S nor i appears in the call under proof's statement or in SETUP. SETUP already may not name a local array or take an address, so S cannot be reached from the call's inputs.
- Anything else in the region except a declaration fails, as before.

**Tests** (tools/tests/test_tools.py; tool tests 147/147):
- Pass:
  - C-02's merged harness (`scan.py --card C-02` on the repository);
  - a toy snapshot loop;
  - a toy constant-index snapshot.
- `RESULT scan FAIL`:
  - `in[0] &= 0x7f;` before the call;
  - S a pointer;
  - S then passed to the call;
  - a loop body with a second statement, in braces or after a comma;
  - S static;
  - S named in SETUP;
  - one counter used by two snapshot loops;
  - a loop counting with `i++`.

`tools/scan.py` on the repository: `RESULT scan PASS 0 problems`. Full gate rerun at bc6cb37 (13-full-gate.log): `RESULT gate all PASS 1008s 0 failed`. In it, scan passed; C-01 proved 675 properties, 0 failed, with coverage 81/81; C-02 proved 1350, 0 failed, with coverage 399/399; and the mutants passed. Builder rule 7, proofs/HOWTO.md, GOAL.md §3.4 and the scan.py docstring give the form.

## Auditor's recheck (REVIEW-LOG.md, 2026-11-08 night): three small items

### 1. A card function's arguments are only `x`, `&x` or `x + y` (scan.py rule 11, `check_card_calls`)

**The rule.** Every use of a card function's name (or of an ENFORCEd one) in a harness must:
- be a call in an entry function, anywhere in it: after the call under proof and inside asserts too;
- have each argument be an identifier, `&identifier` or `identifier + identifier`.

So any narrowing of the inputs sits in SETUP, where the reviewer checks it. Two closures go with it, since each would otherwise get around the rule:
- **Macros.** sqlite3.c function-like macros that expand to a card function count as card functions, transitively (`function_like_macros`, `card_call_names`). For C-02 these are getVarint32, getVarint32NR and putVarint32.
- **Other uses.** Naming a card function other than as a call (a function pointer), or outside an entry function (in a helper or at file scope), fails.

**Today's harnesses already comply.** C-01 calls `putVarint64(output + offset, value)` and `sqlite3PutVarint(output + offset, value)`. C-02 calls `sqlite3PutVarint(buffer, value)`, `sqlite3VarintLen(value)`, `sqlite3GetVarint(encoded, &decoded64)` and `getVarint32(encoded, decoded32)`. `tools/scan.py`: `RESULT scan PASS 0 problems`.

**Tests** (tools/tests/test_tools.py; tool tests 159/159). The ten negative tests all fail on 20ce5b0's scan.py (it printed `RESULT scan PASS`, or for the function pointer only an unrelated problem).
- Pass:
  - a copy of the repository;
  - a toy with `toyGet(p + k)` and `toyGet(&b)` after the call.
- `RESULT scan FAIL`:
  - the auditor's case, C-01 with `sqlite3PutVarint(output + offset, value | 1)`;
  - C-02 with `getVarint32(encoded + 1, decoded32)`, through sqlite3.c's macro;
  - in the toy:
    - `toyGet(p + 1)` as the call under proof;
    - a cast argument;
    - a `?:` argument;
    - a second call `toyGet(q - 1)` after the call under proof;
    - `toyGet(p + 1)` inside an assert;
    - a call through a function pointer;
    - a helper that calls toyGet;
    - a toy sqlite3.c macro `TOYGET(p + 1)`.

### 2. `{model}` and `{effort}` are plain names (campaign.py `role_value_problems`)

A role's model and effort must match `^[A-Za-z0-9._-]+$` and not start with `-`, and must be strings. Three places check it:
- `role_config` raises SessionRefused, which sends the card to triage;
- `start_session` refuses before seeding a config directory or filling the command line;
- `sessions_problems`, so `campaign.py start` refuses the whole sessions.toml.

**Selftest.** Seven new steps cover `--dangerously-bypass-approvals-and-sandbox`, `-o`, `high" -c sandbox_mode="danger-full-access`, `high\n`, `a b`, the empty string and the integer 5, on builder and reviewer. Each checks that all three places refuse and that nothing was spawned or seeded. All seven fail with the check stubbed out to today's behaviour (no check), and pass now.

### 3. The follow-up 7 FIFO check fails instead of hanging (campaign.py `bounded_worktree_read`)

The selftest's in-process reads now run in a thread with a 10 s timeout. A read that has not returned is reported as `hung`; the check then opens the FIFO for writing, which unblocks the read. The check requires every read to be refused by WorktreeFileError: a missing helper, or any other exception, also fails.

**Shown on both versions**, with read_worktree_file replaced by a plain `open()` and run under `timeout 45`:
- 20ce5b0's selftest stopped after the usage checks and was killed (exit 124).
- The new one printed `FAIL a report that is a FIFO or a symlink, …` with `('hung', 'reading reports/C-01-b1.md did not return within 10 s')`, then went on.

### Also: a race in the selftest's phase wait

While testing these, one selftest run gave `RESULT selftest FAIL 60/85` with every phase A card still `waiting` and no session started. The cause:
- `settled()` counts `waiting` as settled, since C-13 waits for good;
- every card also starts in `waiting`;
- so a poll that landed before the daemon's first pass ended phase A at once.

Five later runs passed. A phase now counts as settled only once some session has started for one of its cards. A new selftest step checks that a phase that hasn't started is not settled; it fails with the old `settled()`.

Selftest 86/86 (13-selftest.txt). Builder rule 7, proofs/HOWTO.md, GOAL.md §3.1 and §3.4, and the comment in sessions.toml describe the new rules. GOAL.md §3.1 also said a reviewer could write ~/.claude and ~/.claude.json, which follow-up 6 had stopped; it now says what is writable: the worktree and the reviewer's own config directory.
