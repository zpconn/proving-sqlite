# proving-sqlite, milestone 1 (orchestrator)

Prove with CBMC that 22 functions in SQLite 3.53.4's varint and record decoding have no undefined behavior for any bytes they are given, plus two round-trip properties, on three platform configurations, without changing a byte of SQLite. You are the orchestrator, and two Claude Code sessions play that role in turn. The *setup session* does §0 to §2: it sets up the repo and tools, including `tools/campaign.py`, a plain script that runs the card loop; proves the infrastructure on two pilot cards; prepares the properties and cards; and, after I approve checkpoint 1, freezes them and writes HANDOFF.md. A fresh *campaign session* then does §3 to §5, starting from HANDOFF.md. campaign.py starts the builder and reviewer sessions, commits their work, and merges what reviewers approve once the gate passes. You write the cards, decide what the script can't, and keep the record. You never write proofs. This is a long, multi-session job: don't stop until your part is fully and honestly done, except at the checkpoints below where you must wait for me. If a later instruction from me in chat conflicts with this file, the chat wins. ("proving-sqlite" is a placeholder name.)

**Why it exists.** This is milestone 1 of a proposal to Richard Hipp, SQLite's author: prove SQLite free of undefined behavior one module at a time, with agents doing the proof work, a mechanical checker deciding, and nothing in his tree changing. Hipp has written that formal verification only moves bugs into the design spec. This milestone's answer is that the property is one sentence, and everything else the proofs rest on is written down in LEDGER.md, short enough for him to check. Nothing leaves this machine without my say.

Before designing anything, study:
- **SQLite 3.53.4's amalgamation**, `SQLITE_SOURCE_ID` "2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc": every function in Appendix A at its line, the varint macros at 22361–22369, the serial-value macros at 91930–91934, and the structs Mem, UnpackedRecord, KeyInfo and CollSeq.
- **The record format** in SQLite's file format document (sqlite.org/fileformat2.html, "Record Format"). P3's reference decoder is written from its serial type table.
- **SQLite's AGENTS.md** (github.com/sqlite/sqlite/blob/master/AGENTS.md). Agent-written code is not accepted; agent-found bug reports with a reproducible test case are.
- **Hipp's December 2025 forum replies** on formal verification (sqlite.org/forum/info/39134ba0298d89cf), and the April 2026 follow-up in the same thread on an AI translation of SQLite's B-tree into Rocq, which stalled.
- **CBMC's contract documentation:** the DFCC command line (diffblue.github.io/cbmc/contracts-user-cli.html), loop contracts (diffblue.github.io/cbmc/contracts-loops.html), function contracts, and goto-synthesizer.
- **AWS's proof guide**, "Write a good proof" (github.com/model-checking/cbmc-starter-kit/wiki): coverage, minimal assumptions, assumptions mirrored as runtime assertions, and CBMC's malloc never returning NULL by default.
- **mlkem-native's CBMC proofs** (github.com/pq-code-package/mlkem-native, proofs/cbmc): production C proved memory- and type-safe with per-function contracts and loop invariants. Reuse its harness and Makefile conventions where they fit.

## 0. Ground rules (re-read these after every context reset)

1. **Persistence.** Save this prompt verbatim to `GOAL.md` if it isn't there. Builder and reviewer sessions load `AGENTS.md` too, so it holds only rules every role obeys: this section, condensed, under 150 lines, plus the line "Your role's instructions are in the file your session's prompt names; only the orchestrator acts on the root GOAL.md." Add a one-line `CLAUDE.md` pointing to AGENTS.md. Keep `PROGRESS.md` current: a status block of at most 40 lines (done, in progress, next, open questions), then a dated log, so a fresh session can resume from GOAL.md, AGENTS.md and PROGRESS.md alone. During the campaign, `tools/campaign.py status` and CAMPAIGN.md hold the card-by-card record, and PROGRESS.md points to them. At the handoff, HANDOFF.md (§2) gives the campaign session everything else it needs. Put bulky evidence in files under `evidence/` and summarize each in one line. Delete scratch once its results are archived, and keep it under 5 GB.
2. **SQLite is the code under proof, unchanged.** `upstream/` holds the pinned sqlite3.c and sqlite3.h byte for byte, and the matching source release, all hashed in `pin.txt`. `overlay/sqlite3.c` is upstream plus `PROOF(...)` spans and nothing else; `tools/check_overlay.py` deletes every PROOF span and requires what remains to equal upstream byte for byte. Harnesses call SQLite's own functions in the overlay. No agent copies, rewrites or edits SQLite code.
3. **Frozen files.** At checkpoint 1, `proof.lock` records SHA-256 hashes of pin.txt, upstream/, GOAL.md, AGENTS.md, CLAUDE.md, agents/, PROPERTIES.md, TRUSTED.md, UB-CLASSES.md, proofs/spec/, proofs/CHECKS, proofs/CONFIGS, proofs/MUTANTS, tools/ and the gate's Makefile targets, and the gate checks them. The one exception in tools/ is `sessions.toml`, because CLI flags change; it may hold only command lines, model names and usage-limit patterns. Changing a frozen file afterwards needs my approval: write the patch and its evidence under `evidence/approvals/`, ask me, and leave it unapplied until I answer.
4. **Never weaken.** No agent weakens a property, check, configuration, mutant, gate or ledger statement to make a proof pass. Propose the change under §0.3 instead.
5. **Name the kind of claim.** *Proved*: CBMC verified it under the frozen checks. *Tested*: runtime evidence. *Assumed*: a LEDGER.md entry. *Trusted*: listed in TRUSTED.md (CBMC, its C semantics and library models, the preprocessor). Every status line, report and result uses these four words, and uses them exactly.
6. **Roles stay separate.** Builders write proofs and reviewers judge them; you never write or fix one, not even in the pilot. campaign.py schedules sessions, commits their work, merges and gates; you decide what it can't. Nobody reviews their own work. A reviewer runs in a fresh session, on the other vendor from the one that built the round it judges, and sees only the artifacts, never the builder's transcript. campaign.py refuses to start one otherwise.
7. **Nothing leaves the machine.** Don't push, publish, post to the SQLite forum, email anyone or file bug reports. Findings stay in FINDINGS.md until I decide. Add no license file; I'll decide licensing after a legal review.
8. **Budgets.** Every card has a token cap (Appendix B), and the milestone's cap is 1B tokens. A token is anything a CLI reports: input, cache reads and writes, and output. campaign.py stops a session at its card's cap and records every session it starts in `evidence/tokens.csv`. Record your own sessions in `evidence/orchestrator/tokens.csv` at each checkpoint.
9. **The machine.** Run CBMC and agent sessions under `nice -n 10`. Run at most 4 builder and reviewer sessions at once, together, and fewer if CBMC makes the machine swap. Give every CBMC run a timeout, starting at 10 minutes per configuration.
10. **Models and subscriptions.** Builders run on Codex with GPT-6 Astra (`gpt-6-astra`): xhigh reasoning effort on high-tier cards, high on standard ones. Reviewers run on Claude Code, Opus 5.5 on high-tier cards and Sonnet 5.5 on standard ones. The ledger agent, both orchestrator sessions and the auditor run on Claude Code with Opus 5.5. Every session runs on my Claude or ChatGPT subscription, through that vendor's own CLI signed in with my account: `claude -p` and `codex exec`. Use no API keys. A key in the environment can take precedence over the login, so campaign.py strips API-key variables from every session's environment, and no session uses a flag that needs a key, such as claude's `--bare`. Drive neither model through any other tool. Usage limits set the pace: a session stopped by a limit resumes after the reset, and that doesn't count against its card.
11. **Who commits to main.** `tools/campaign.py start` moves your checkout to branch `orch` and gives main its own checkout at `../proving-sqlite-wt/main`; `tools/campaign.py finish` reverses that. In between, only campaign.py commits to main. You commit on orch and send your commits with `tools/campaign.py land`. Every commit campaign.py makes carries a `Campaign:` trailer saying what it is and what checked it, its merges of main into card branches and into orch included.

## 1. Bring-up and pilot

Set up the repo (Appendix D), pins and tools, and test what this plan assumes about them. Record each item with its evidence in PROGRESS.md and `evidence/bringup/`.

1. **Pins.** The SQLite 3.53.4 amalgamation, checking SQLITE_SOURCE_ID against the value above; its source release (sqlite-src-3530400.zip), which holds the test suite the ledger agent runs offline; and the latest CBMC release, recording its version and solver back ends. If SQLite has a newer release, still pin 3.53.4, because Appendix A was checked against it, and tell me.
2. **Contracts on separate declarations.** The DFCC command line accepts `--enforce-contract <function>[/<contract>]` and `--replace-call-with-contract <function>[/<contract>]`, but its documentation doesn't say what the suffix means. On a toy, show whether `f/c` checks f against clauses declared on a separate declaration c, fails when c's ensures is false of f, and replaces calls to f with c. If it works, contracts live in `proofs/contracts/` and SQLite's text gets only loop annotations. If not, contracts become PROOF spans on the definitions in the overlay. Record the choice.
3. **Loop contracts.** Define `#define PROOF(...) __VA_ARGS__` in `proofs/include/proof.h`. On a toy while loop and a toy do-while (sqlite3VdbeRecordCompareWithSkip's loop is a do-while), show that `__CPROVER_assigns`, `__CPROVER_loop_invariant` and `__CPROVER_decreases`, in that order between header and body (for a do-while, between `do` and the body: CBMC 6.11 does not parse them after the condition, and the invariant must hold at the top of every iteration), are applied by `--apply-loop-contracts`, and that a false invariant and a non-decreasing measure are each caught. The documentation shows only inline loop contracts. goto-synthesizer can dump synthesized ones as JSON, but nothing documented reads them back, so assume inline.
4. **Checks.** Write `proofs/CHECKS`, the CBMC options every proof uses: pointer, bounds, signed overflow, undefined shift, division by zero, pointer overflow and pointer primitive checks; a float-to-integer conversion check if your CBMC has one (6.11 has none on its own: `--conversion-check` also flags conversions C defines, so CHECKS runs it as a second pass restricted to its float-to-integer properties); malloc that may fail and return NULL; and unwinding assertions. Confirm each option in `cbmc --help`, then show each check fires on a toy that commits its UB. Write `UB-CLASSES.md`: every kind of undefined behavior in C11 Annex J.2 that can arise in this code, each marked *checked* (by which option), *argued* (by inspection, listing the sites, e.g. serialGet's `*(i64*)&x` and sqlite3GetVarint's `(signed char*)p`) or *out of scope* (data races, since the proofs assume one thread; stack exhaustion), with the reason.
5. **Configurations.** `proofs/CONFIGS` defines lp64-le, ilp32-le and lp64-be. lp64-be also passes `-DSQLITE_BYTEORDER=4321` when preprocessing, and `-funsigned-char`, since PowerPC's plain char is unsigned; it must not pass `-m64`, which resets goto-cc to little-endian. ilp32-le needs gcc-multilib's 32-bit headers. For each, show with a probe harness, and by preprocessing the overlay, that the word size, the endianness, the signedness of plain char and SQLite's byte-order branches are what the name says. Hipp tests on a big-endian PowerPC, among others.
6. **Builds.** Time goto-cc on the whole overlay per configuration, and decide how proofs link against it, e.g. one sqlite3 goto binary per configuration, with each harness linked in and unused functions dropped. Record the time and memory. Builds write only inside the worktree they run in, because a Codex session can write nowhere else, and .gitignore covers everything they write.
7. **Coverage.** Find the command that reports which lines of the function under proof a harness reaches. Show that it flags a deliberately unreachable line in a toy.
8. **Native probes.** Build these with ASan and UBSan against unmodified upstream, not with CBMC:
   1. Varints: round-trip boundary values and a million random values through sqlite3PutVarint and sqlite3GetVarint, and print sqlite3VarintLen at 2^63−1, 2^63 and 2^64−1. Reading the source, it returns 10 for v ≥ 2^63, though the encoding is 9 bytes. This settles P2's wording.
   2. Over-read: call sqlite3VdbeRecordUnpack on the two-byte record {0x02, 0x81} held in an exact-size malloc. Reading the source, decoding the serial type reads past the record, so ASan should report a heap-buffer-overflow read. This is the premise of ledger entry A-001.
9. **Tools.**
   - `tools/check_overlay.py`.
   - `tools/scan.py` (§3.4).
   - `tools/mutate.py`, which applies one mutant to a scratch copy of the overlay and always restores the original.
   - Top-level `make prove`, `make coverage`, `make gate` and `make gate CARD=C-NN` (§3.4). `make -C proofs/C-NN prove` takes `CONFIG=<name>` to run one configuration. Every target ends its output with one result line, such as `RESULT prove C-03 lp64-le PASS 212s 1843 properties 0 failed`, so a run cut off by a shell timeout can't pass for a result. (`make -C` prints "Leaving directory" after it unless `GNUMAKEFLAGS=--no-print-directory` is set, as campaign.py sets it for every session and gate.)
10. **Agent CLIs.** From `claude --help` and `codex exec --help`, write `tools/sessions.toml`: for each vendor, role and tier, the command that starts a headless session in a given directory, with its model and effort, no permission prompts (for Codex, the workspace-write sandbox) and JSON output. On a toy task in a scratch worktree, show for each CLI that:
    1. a session runs to the end without prompts, on my subscription login, with no API-key variable set, and the CLI's own output or status command confirms the login;
    2. its token usage can be read while it runs, or at least when it ends;
    3. a killed session resumes and carries on (`claude -p --resume`, `codex exec resume`);
    4. it can run a 15-minute command and read the result, following the long-run rule in agents/builder/GOAL.md;
    5. a Codex session can run CBMC and write in its worktree, but can't write .git or reach the network.

    Also record what each CLI prints, and its exit status, when a usage limit stops it, from its documentation or a real occurrence, and put the patterns in sessions.toml. If a CLI reports token usage only when a run ends, find a running count elsewhere, such as the session log Codex writes as it goes. If there is none, campaign.py enforces that CLI's caps as time limits instead: each card's cap divided by the tokens per hour the pilot measured for its tier. Record which applies.
11. **Coordinator.** Write `tools/campaign.py` as §3.1 describes. Test it in a scratch clone with fake CLIs: scripts in `tools/fakecli/` that stand in for claude and codex and leave canned reports and verdicts. Show that it handles:
    - a card approved and merged, and a rejection whose second round answers the review;
    - three rejections, a crash that it resumes, and three crashes in one round;
    - a usage limit, which pauses that vendor until the reset without counting against the card;
    - a builder that changes or commits a file outside its card's May change line, and a reviewer that changes any tracked file;
    - a gate failure after APPROVE, and a session that reaches its cap;
    - a card whose dependency isn't merged, a land that touches proofs/, and a reviewer on the builder's vendor;
    - `kill -9` mid-session and mid-merge, then a restart that neither loses nor repeats work.

    `tools/campaign.py selftest` reruns all of these in a scratch directory of its own, so it can run from any clone without touching a live campaign.
12. **Pilot.** Run `tools/campaign.py start --cards C-01,C-02`. campaign.py builds both cards with Astra builder sessions, starts Claude reviewers for them, and merges what they approve. Kill C-02's builder once mid-session and show that it resumes. Plant a bug in a scratch copy of putVarint64 and show that a proof fails. Then run `tools/campaign.py finish`. PROPERTIES.md doesn't exist yet, so both cards quote their property from §2. If a tool needs fixing mid-pilot, run finish, fix it on main, and start again; card state carries over. If Astra can't finish a pilot card in three rounds, say so at checkpoint 0 rather than building it yourself.

**Checkpoint 0.** Stop and wait for me. PROGRESS.md lists each item above with its result and evidence, the contract-location choice, the pilot's numbers (CBMC time per configuration, properties checked, coverage, rounds, and tokens and hours per session), and anything in this file that bring-up showed to be wrong. Print its status block and the selftest's output.

## 2. Properties and freeze

Write PROPERTIES.md with these statements. Change them only where bring-up showed this file wrong, and say where.

**P1. No undefined behavior.** For each function f in Appendix A, with in-scope callees replaced by their proved contracts and boundary callees by contracts recorded in LEDGER.md, CBMC proves f's harness on every configuration, with every option in proofs/CHECKS and no failed property. That is: under f's requires, f triggers no check, its ensures hold, it writes only what its assigns lists, and every loop keeps its invariant and decreases its measure. Requires may state sizes, allocation, aliasing and the values of struct fields. They never constrain data bytes: those of a record or page being decoded, or the string and blob contents a Mem points at. A decoder whose read extent depends on data bytes gets its worst-case footprint (9 bytes for a varint).

**P2. Varints round-trip.** For every u64 v:
- sqlite3PutVarint writes n bytes, 1 ≤ n ≤ 9, and nothing else.
- sqlite3GetVarint on those bytes returns n and v.
- `getVarint32` returns n and v when v ≤ 0xffffffff, and n and 0xffffffff otherwise.
- sqlite3VarintLen(v) is n for v < 2^63 and 10 for v ≥ 2^63, or whatever §1.8.1 measured. State what the code does; don't round it off.

**P3. Serial values decode as the file format says.** For every serial type t, and any bytes b of which the first k are readable, where k is t's size in the file format table for t ≤ 11 and 0 for t ≥ 12, sqlite3VdbeSerialGet(b, t, m) leaves in m what `ref_serial_get` in proofs/spec/record_format.h says. That reference is written from the file format's serial type table in at most 60 lines, each case citing its row, with SQLite's departures written out:
- A NaN double decodes as NULL.
- Types 10 and 11 follow the code: NULL with MEM_Zero, and NULL.
- For t ≥ 12, nothing is read, and m points at b with length (t−12)/2: a blob if t is even, text if it is odd.

Also prepare:
1. Appendix A confirmed against the pin, with each function's direct callees from the call graph and the order the cards will run in.
2. proofs/spec/record_format.h, checked against the file format document by a reviewer session on the vendor that didn't write it (`tools/campaign.py session`).
3. LEDGER.md drafts for the three boundary contracts and for A-001, in the Appendix C format.
4. proofs/MUTANTS: at least two mutants per function, each a one-token change to a bounds check, mask, shift, constant or loop condition. A mutant is killed when some proof fails. Each line names, with `card=`, the card whose proofs must kill it, so a card's gate never waits on a card that merges later; the full gate runs every mutant against every proof. List any you expect to be equivalent, and why.
5. A card for every function (Appendix B), with its Depends on and May change lines.
6. TRUSTED.md and UB-CLASSES.md.

**Checkpoint 1.** Stop for my review with all of the above ready, and print the list with each item's file. Don't write proof.lock or start §3.

**The handoff.** When I approve checkpoint 1, commit proof.lock, then write and commit HANDOFF.md. It holds everything a fresh session needs besides this file, AGENTS.md and PROGRESS.md, on one screen plus links:
- **State:** each checkpoint and when I approved it, the proof.lock commit, and what `tools/campaign.py status` shows (C-01 and C-02 merged; the rest waiting or ready).
- **What bring-up decided or found:** the contract-location choice, the CBMC version and solvers, how each CLI's usage is counted, the usage-limit patterns, the pilot's numbers, and anything in this file it showed to be wrong.
- **Checks for the campaign session to run first:** `make gate CARD=C-02` passes, lock check included; `tools/campaign.py selftest` passes; `tools/campaign.py status` matches the state above.
- **Open questions and known issues.**
- **Where everything is,** by path.

Then print HANDOFF.md and stop. The setup session ends there, and the campaign session does §3 onward.

## 3. The proof campaign

The campaign session starts here. Read HANDOFF.md and run the checks it lists; if any fails, stop and tell me. Then run `tools/campaign.py start`. campaign.py runs the loop below unattended, in a tmux session named `campaign`, and you handle its triage queue.

1. **What campaign.py does.** It's a plain program with no model in its loop, frozen with tools/ at checkpoint 1. Appendix E lists the card states.
   - **Order.** A card is ready when every card on its Depends on line is merged. Ready cards start in card order, within §0.9's limit, and never on a vendor that is waiting out a usage limit.
   - **Worktrees.** A builder works in `../proving-sqlite-wt/C-NN` on branch `card/C-NN`, and each round starts by merging main into that branch; a conflict sends the card to triage. A reviewer gets a fresh worktree, detached at the commit it judges, which is deleted afterwards.
   - **Sessions.** Each starts from tools/sessions.toml, detached in its own process group under `nice -n 10`, with its output streamed to `../proving-sqlite-wt/state/` and its exit status written beside it, so it outlives a restart of campaign.py. Builders run on Codex and reviewers on Claude, at the card's tier, as §0.10 says; campaign.py fixes the vendors and sessions.toml supplies the models and command lines. Codex runs in its workspace-write sandbox. Claude runs in `--permission-mode auto` inside bubblewrap, which leaves only its worktree, ~/.claude and ~/.claude.json writable and hides /tmp, ~/.codex, state/, the other worktrees and the primary checkout; campaign.py refuses a command line without these. The prompt is fixed in campaign.py: the role's GOAL file, the card, the round and any reviews to answer. `tools/campaign.py session` starts a one-off session the same way, for the §2 spec review and the ledger agent. It commits what the session writes, checked against the paths that role may write, on a branch of its own, and during a campaign lands it on main.
   - **Commits.** Sessions don't write git. When a builder ends, campaign.py checks every change since the round started, committed or not, including new files git doesn't ignore. If all are on the card's May change line, and none adds a symlink or changes a file mode, it commits them with a message naming the card and round; otherwise it commits nothing and sends the card to triage. When a reviewer ends, it commits only the review file: onto the card branch, or onto main for a re-review of a merged card. A reviewer that changed a tracked file is discarded and run once more, and if that one does too, the card goes to triage.
   - **Verdicts.** The first line of the report or review decides. DONE and FINDING start a reviewer. APPROVE sends the card to merge, or, on a FINDING, to triage with the finding reproduced. REJECT starts the next builder round, up to three. Anything else goes to triage: STUCK, NEEDS-DECISION, NEEDS-ZACH, a third REJECT, or a missing first line.
   - **Merges,** one at a time. campaign.py merges only the commit the reviewer approved, plus the review. In a scratch worktree at main's head, it merges them with `--no-ff`, checks that the merge touches only the card's May change paths and its own reviews, and runs `make gate CARD=C-NN`. If that passes, it regenerates RESULTS.md, results.csv, CAMPAIGN.md and evidence/tokens.csv, adds the gate log under evidence/gate/, commits them, and fast-forwards main. If not, the card goes to triage with the gate log. After the last card merges, it runs the full `make gate`.
   - **Interruptions.** A session that ends without its report or verdict is resumed in the same worktree. If its output matches its vendor's usage-limit pattern, no session starts on that vendor until the reset time it printed, or, if it printed none, for 30 minutes, doubling up to 4 hours; that doesn't count against the card. A session whose output matches its vendor's auth-failure pattern, an expired or revoked login, is handled the same way, except that the vendor stays paused until I sign in again: campaign.py adds a triage item asking for that, and `tools/campaign.py resume-vendor <vendor>` lifts the pause once the CLI's login check passes. Any other interruption counts, and the third in a round sends the card to triage. Output that matches no pattern is logged verbatim, so the patterns can be fixed.
   - **Caps.** It counts each session's tokens as §0.8 defines them, or its time where §1.10 found no running count, and keeps the running total in `.campaign/usage` in the session's worktree, where builders read it. At the card's cap it ends the session, commits a builder's allowed changes, and sends the card to triage.
   - **Restarts.** It journals each step in `../proving-sqlite-wt/state/` before taking it. On restart it reconciles the journal with git and the running sessions, so a crash at any point neither loses nor repeats a session or a merge. `tools/campaign.py stop` stops it starting anything new; running sessions carry on, and `start` picks up where it left off.
   - **Status.** `tools/campaign.py status` prints each card's state, round, vendor, tokens against cap and what it is waiting on, then the triage queue, the merge queue, any vendor pause and the last full gate's result. CAMPAIGN.md holds the same.
2. **What you do.**
   - Run `tools/campaign.py wait` in the background. It returns when the triage queue changes, the campaign finishes, campaign.py stops, or four hours pass, so you never poll.
   - Take each triage item in turn and read its report, review and logs. Then fix the card, land the fix, and run `tools/campaign.py retry C-NN`; reopen another card (§3.3); or run `tools/campaign.py park C-NN` and put the question under Open questions in PROGRESS.md, with your recommendation. STUCK and FINDING cards always get a recommendation.
   - Commit your own changes on branch orch, then run `tools/campaign.py land`. It merges main into orch, so your checkout stays current, and queues orch for main. A land may touch only cards/, tests/repro/, evidence/approvals/, evidence/orchestrator/, PROGRESS.md, LEDGER.md and FINDINGS.md. A frozen file may change only with my approval record and an updated proof.lock in the same land; campaign.py then runs the full gate and sends every card whose proof fails to triage. Proofs reach main only through card merges.
   - campaign.py is frozen. If it misbehaves, stop it and ask me before changing it.
3. **Contract changes.** A builder that needs more from an approved contract, such as a stronger ensures or a weaker requires, reports NEEDS-DECISION with the change. If you agree, `tools/campaign.py reopen C-NN --for C-MM` sends C-NN, the card that owns the contract, back for a new round with the request added to its notes, and C-MM waits for it. When C-NN merges again, its gate has rerun every proof that uses the contract, and campaign.py starts a re-review of each merged card whose proof uses it. A REJECT sends that card back for a new round.
4. **The gate.** `make gate` runs everything below. `make gate CARD=C-NN`, which campaign.py runs before each merge, runs check_overlay, the proof.lock check and scan.py, plus the include check, proofs, coverage and mutants of the card and of every card whose proofs call its functions, and, if proofs/include/preds.h changed, of every card that includes it.
   - check_overlay;
   - proof.lock's hashes; after the freeze, a missing proof.lock fails;
   - each harness, preprocessed on every configuration, includes only overlay/sqlite3.c, proofs/include/*.h, proofs/contracts/*.h, proofs/spec/*.h and system headers;
   - every merged proof, on every configuration, with proofs/CHECKS;
   - coverage of every proof, with each unreached line of the function under proof listed under "Unreached lines" in its NOTES.md, and every function of each card in some proof's COVER;
   - every mutant in proofs/MUTANTS killed, or shown equivalent by a reviewed argument;
   - `tools/scan.py`, which rejects:
     - any `__CPROVER_assume` outside a harness's setup block;
     - any option that turns a check off, and any compile flag beyond proofs/CONFIGS;
     - unwinding without unwinding assertions;
     - a boundary contract that doesn't name its ledger entry;
     - a harness that defines a function SQLite's code calls;
     - a PROOF span anywhere but where §1.2 and §1.3 allow, in the functions its card names, or one that holds anything but contract clauses;
     - abort, exit, _Exit, longjmp, __VERIFIER_* and __CPROVER_array_set/array_replace in harnesses, predicates, specs and contracts;
     - return or goto in a harness entry function, and anything but exactly one SETUP block per entry function, before the call under proof;
     - any file in proofs/C-NN/ but harness.c, Makefile and NOTES.md, and any symlink under proofs/, overlay/ or tests/repro/;
     - a change to preds.h other than new predicates;
   - the P2 and P3 harnesses.
5. **Ledger and findings.** Builders draft entries. Once a reviewer has checked a draft, you number it and land it in LEDGER.md or FINDINGS.md, copying a finding's repro to `tests/repro/F-NNN.c`. A finding is a counterexample that reproduces: `tests/repro/F-NNN.c` builds natively against unmodified upstream/sqlite3.c and fails under ASan or UBSan. A reviewer reproduces each one before it goes in.
6. **Results.** RESULTS.md and results.csv give, for each function, property and configuration: CBMC time, properties checked, coverage, mutants killed, the review verdict and the ledger entries used. campaign.py generates them from evidence at each merge; never edit them by hand.

## 4. Ledger validation

When the boundary contracts and A-001 have settled, install the ledger agent's build needs, such as Tcl's development files, because its session may have no network. Then start it (agents/ledger/GOAL.md) with `tools/campaign.py session ledger`. It tests the assumptions against SQLite's own test suite and fuzz corpora, built from the pinned source release, and reports each entry as tested or violated. campaign.py lands its validation/ and evidence/ledger/ files and its report. A violated entry is either a wrong assumption, which gets fixed through a card, or a finding (§3.5).

## 5. Final gate

1. Run `tools/campaign.py finish`, which stops campaign.py, removes its checkout, and returns yours to main with orch merged. Then, from a clean clone, `make gate` passes and results.csv regenerates identically. Record the wall time.
2. Write README.md for a reader like Hipp. It says what is proved, about which check-in, under which checks and configurations; what is assumed (LEDGER.md) and trusted (TRUSTED.md); what is out of scope (UB-CLASSES.md); the findings; and how to run it. One screen, then links. No adjectives; use the §0.5 words.

**Checkpoint 2.** Stop for my review, and print the clean-clone gate's result line and the results.csv comparison. I'll run the auditor. Don't publish or contact anyone.

## 6. Reasoning already settled

- **CBMC, not Frama-C/WP.** Its bit-precise semantics suit varints, shifts, and serialGet's cast and memcpy into a double. Failures come back as concrete counterexamples, which is the reproducible test case SQLite's AGENTS.md asks for. AWS and mlkem-native use it this way in production. Frama-C/WP may fit milestone 2's freeblock lists better; decide then.
- **Not Lean.** There is no Aeneas for C. A Lean model of the C would reintroduce the AI translation step on which the April 2026 Rocq attempt stalled, and the pitch promises proofs about the C as written.
- **Not machine code yet.** Proving compiled binaries, as Anthropic did for OSS-Fuzz libraries in October 2026, matches Hipp's stated view that the machine code is what matters, but it covers one build. Revisit after milestone 1.
- **Default compile options, with asserts compiled out**, as SQLite ships. SQLite's own asserts aren't part of P1.
- **Scope.** sqlite3VdbeIdxKeyCompare, sqlite3VdbeIdxRowid and the sorter's varint helpers reach into B-tree cursors and files, so they open milestone 2. vdbeCompareMemString calls the application's collation callback or converts encodings, so it stays a boundary contract.
- **One thread.** Data races are undefined behavior, and the default build is threadsafe, but proving race freedom is a different kind of proof. P1 assumes single-threaded use, as Anthropic's binary proofs did, and UB-CLASSES.md says so.
- **The ledger is the product.** It's the only place a spec can be wrong, which is Hipp's objection. The answer is to keep it short and explicit, and to test it.
- **A script runs the loop, not a model.** Over days, a model polling sessions drifts and spends its context on waiting. A script doesn't, and its merge rule can be frozen and audited. It also runs outside Codex's sandbox and keeps each vendor in its own CLI, signed in as me. The models do what needs judgment: proofs, reviews and triage.
- **A fresh session runs the campaign.** The setup session's context fills with bring-up detail the campaign doesn't need, and a session that starts from HANDOFF.md alone proves the handoff is complete.
- **Astra builds, Claude judges.** Builders spend the most tokens, so this puts the heaviest load on the ChatGPT subscription, and every proof is judged by a different model family from the one that wrote it.

## Appendix A. Scope

SQLite 3.53.4 amalgamation. *Line* is the line that names the function (corrected at checkpoint 0: the table first gave the line after it, and 191392 for sqlite3CorruptError). *UB sites* counts the memory accesses AddressSanitizer instruments at -O1 plus UBSan's arithmetic and pointer checks, measured on this pin; use it for budgeting only. The 22 functions total about 800 lines, 7 loops and 570 UB sites.

| Level | Function | Line | NLOC | Loops | UB sites | Calls in scope | Boundary calls |
|---|---|---|---|---|---|---|---|
| 0 | sqlite3VarintLen | 38215 | 7 | 1 | 2 | | |
| 0 | putVarint64 | 37967 | 25 | 3 | 23 | | |
| 0 | sqlite3GetVarint | 38021 | 106 | 0 | 51 | | |
| 0 | sqlite3VdbeSerialTypeLen | 91862 | 9 | 0 | 4 | | |
| 0 | sqlite3VdbeOneByteSerialTypeLen | 91871 | 5 | 0 | 3 | | |
| 0 | serialGet | 91945 | 20 | 0 | 34 | | |
| 0 | serialGet7 | 91980 | 18 | 0 | 34 | | |
| 0 | vdbeRecordDecodeInt | 92552 | 33 | 0 | 76 | | |
| 0 | sqlite3VdbeFindCompare | 93010 | 34 | 0 | 22 | | |
| 0 | isAllZero | 92369 | 7 | 1 | 3 | | |
| 0 | sqlite3IsNaN | 36445 | 8 | 0 | 5 | | |
| 0 | sqlite3VdbeMemSetNull | 86607 | 7 | 0 | 2 | | |
| 1 | sqlite3PutVarint | 37991 | 12 | 0 | 7 | putVarint64 | |
| 1 | sqlite3GetVarint32 | 38182 | 23 | 0 | 16 | sqlite3GetVarint | |
| 1 | sqlite3VdbeSerialGet | 91997 | 68 | 0 | 72 | serialGet | |
| 1 | sqlite3IntFloatCompare | 92425 | 16 | 0 | 1 | sqlite3IsNaN | |
| 1 | sqlite3VdbeAllocUnpackedRecord | 92096 | 15 | 0 | 9 | | sqlite3DbMallocRaw |
| 2 | sqlite3VdbeRecordUnpack | 92116 | 41 | 1 | 20 | sqlite3GetVarint32, sqlite3VdbeSerialGet, sqlite3VdbeSerialTypeLen, sqlite3VdbeMemSetNull | |
| 2 | sqlite3VdbeRecordCompareWithSkip | 92607 | 198 | 1 | 73 | sqlite3GetVarint32, sqlite3VdbeSerialGet, serialGet7, sqlite3VdbeSerialTypeLen, sqlite3VarintLen, vdbeRecordDecodeInt, sqlite3IntFloatCompare, isAllZero | vdbeCompareMemString, sqlite3CorruptError |
| 3 | sqlite3VdbeRecordCompare | 92828 | 6 | 0 | 0 | sqlite3VdbeRecordCompareWithSkip | |
| 3 | vdbeRecordCompareString | 92940 | 61 | 0 | 24 | sqlite3GetVarint32, sqlite3VdbeRecordCompareWithSkip | sqlite3CorruptError |
| 4 | vdbeRecordCompareInt | 92845 | 76 | 0 | 86 | sqlite3VdbeRecordCompare, sqlite3VdbeRecordCompareWithSkip | |

memcmp, called by sqlite3VdbeRecordCompareWithSkip and vdbeRecordCompareString, is CBMC's library model, so it goes in TRUSTED.md.

Boundary contracts are assumed, and each needs a LEDGER.md entry:

| Function | Line | Used by | Why it's not proved here |
|---|---|---|---|
| sqlite3DbMallocRaw | 32113 | sqlite3VdbeAllocUnpackedRecord | The allocator and lookaside belong to a later milestone. Contract: returns NULL or a fresh block of at least n bytes. |
| vdbeCompareMemString | 92350 | sqlite3VdbeRecordCompareWithSkip | It calls the collation's xCmp, which is application code, or converts encodings through vdbemem.c. |
| sqlite3CorruptError | 191373 | sqlite3VdbeRecordCompareWithSkip, vdbeRecordCompareString | It reports through sqlite3_log, which can call the application's log callback, and returns SQLITE_CORRUPT. |

Facts read from the source on 2026-11-04, for card notes. The §1.8 probes check the sqlite3VarintLen and sqlite3VdbeRecordUnpack facts.
- sqlite3GetVarint takes no length and reads up to 9 bytes. It is straight-line code.
- The `getVarint32` macro handles a one-byte varint inline and calls sqlite3GetVarint32 only when the first byte is at least 0x80. sqlite3GetVarint32 reads p[1] and p[2], then calls sqlite3GetVarint for four or more bytes.
- putVarint64 writes up to 9 bytes through a local `buf[10]`; each of its loops runs at most 9 times.
- sqlite3VarintLen returns 10 for v ≥ 2^63. Its callers in scope pass serial types, which are u32.
- serialGet reads a u64 object through an `i64*`, which C allows because i64 is the signed type corresponding to the effective type. It copies into the double `pMem->u.r` with memcpy, and a NaN becomes MEM_Null.
- sqlite3VdbeSerialGet reads nothing for serial types of 12 or more. It sets z and n, and indexes its two-entry `aFlag` with `serial_type&1`.
- sqlite3VdbeMemSetNull frees memory only for a dynamic Mem. RecordUnpack's Mems come from SerialGet and never are, so its contract requires `!VdbeMemDynamic(pMem)` and the call site proves it.
- sqlite3IntFloatCompare guards its `(i64)r` conversion with range checks. It is the one float-to-integer conversion in scope.
- sqlite3VdbeRecordUnpack's loop tests `idx<szHdr` and `d<=nKey` before each field, but nothing bounds how far the varint at `aKey[idx]` or the value at `aKey[d]` extends. A corrupt record therefore makes the decoders read past pKey+nKey, and the comment at 92150–92153 notes that the last Mem may then hold uninitialized memory. The proof needs a slack requires: ledger entry A-001, which says callers provide readable bytes after the record. Determine the smallest slack that works.

## Appendix B. Cards

A card is `cards/C-NN.md`:
~~~
# C-NN: <functions>
- Property: P1 | P2 | P3
- Functions: <name> (upstream/sqlite3.c:<line>), ...
- In-scope callees, with approved contracts: ...
- Boundary callees, with ledger entries: ...
- In-scope callers, whose call sites must satisfy the requires: ...
- Depends on: C-..
- May change: <each path builder §1 allows this card, spelled out>
- Cap: builder <tokens>; reviewer half that. Tier: high | standard
- Notes: the relevant Appendix A facts; open issues from earlier rounds
~~~
Tier *high* means Astra at xhigh effort for the builder and Opus 5.5 for the reviewer; *standard* means Astra at high effort and Sonnet 5.5 (§0.10). tools/sessions.toml maps tiers to models. campaign.py reads the Depends on, May change, Cap and Tier lines, so keep their format.

| Card | Functions | Property | Cap | Tier |
|---|---|---|---|---|
| C-01 | sqlite3PutVarint, putVarint64 (pilot) | P1 | 10M | standard |
| C-02 | round-trip harness (pilot) | P2 | 10M | standard |
| C-03 | sqlite3GetVarint | P1 | 20M | high |
| C-04 | sqlite3GetVarint32 | P1 | 10M | standard |
| C-05 | sqlite3VarintLen | P1 | 5M | standard |
| C-06 | sqlite3VdbeSerialTypeLen, sqlite3VdbeOneByteSerialTypeLen | P1 | 5M | standard |
| C-07 | serialGet, serialGet7 | P1 | 10M | standard |
| C-08 | sqlite3VdbeSerialGet | P1 | 20M | standard |
| C-09 | serial decoding harness | P3 | 20M | high |
| C-10 | vdbeRecordDecodeInt | P1 | 10M | standard |
| C-11 | sqlite3IsNaN, sqlite3IntFloatCompare | P1 | 10M | standard |
| C-12 | isAllZero | P1 | 5M | standard |
| C-13 | sqlite3VdbeMemSetNull | P1 | 5M | standard |
| C-14 | sqlite3VdbeAllocUnpackedRecord | P1 | 10M | standard |
| C-15 | sqlite3VdbeRecordUnpack | P1 | 60M | high |
| C-16 | sqlite3VdbeFindCompare | P1 | 10M | standard |
| C-17 | sqlite3VdbeRecordCompareWithSkip | P1 | 80M | high |
| C-18 | sqlite3VdbeRecordCompare | P1 | 5M | standard |
| C-19 | vdbeRecordCompareString | P1 | 30M | high |
| C-20 | vdbeRecordCompareInt | P1 | 30M | high |

## Appendix C. Ledger and finding entries

~~~
## A-NNN <short name>
- Function(s):
- Clause, as CBMC states it:
- Plain English:
- Why the proof needs it:
- Who must make it true: callers in milestone N | the application | the allocator or OS
- Evidence: none | tested (ledger agent run <date>: N checks, 0 violations; sites reached)
- Status: draft | reviewed | tested | violated | retired
~~~
~~~
## F-NNN <short name>
- Function, line, failing check, configuration:
- Counterexample (arguments and bytes):
- Repro: tests/repro/F-NNN.c, built natively against unmodified upstream with ASan/UBSan; command:
- Reachable from SQL or the public API? unknown | yes (how) | only if ledger entry A-NNN is violated
- Status: draft | reproduced | not a bug (why)
~~~

## Appendix D. Layout

~~~
GOAL.md AGENTS.md CLAUDE.md PROGRESS.md HANDOFF.md CAMPAIGN.md PROPERTIES.md
LEDGER.md FINDINGS.md RESULTS.md results.csv TRUSTED.md UB-CLASSES.md README.md pin.txt proof.lock
upstream/         sqlite3.c, sqlite3.h and the source release, at the pin
overlay/          sqlite3.c with PROOF spans only
proofs/           CHECKS, CONFIGS, MUTANTS, Makefile.common
proofs/include/   proof.h, preds.h (shared predicates)
proofs/contracts/ <function>.h
proofs/spec/      record_format.h
proofs/C-NN/      harness.c, Makefile, NOTES.md
cards/ reports/ reviews/
tests/repro/      F-NNN.c
tools/            check_overlay.py, scan.py, mutate.py, campaign.py, sessions.toml, fakecli/
validation/       the ledger agent's instrumented build
evidence/         including handover/, bringup/, gate/, tokens.csv, approvals/, orchestrator/, ledger/
agents/           builder/GOAL.md, reviewer/GOAL.md, ledger/GOAL.md

../proving-sqlite-wt/   outside the repo
  main/           campaign.py's checkout of main during the campaign
  C-NN/           builder worktrees, on card/C-NN
  C-NN-r<k>/      reviewer worktrees, detached
  merge/          scratch for merge gates
  state/          campaign.py's journal and the session logs
~~~

## Appendix E. Card states

| State | Meaning | Moves to |
|---|---|---|
| waiting | A card on its Depends on line isn't merged. | ready |
| ready | Queued for a builder. | building |
| building | A builder round is running, or waiting out a usage limit. | reviewing, triage |
| reviewing | A reviewer is judging the round, or re-reviewing a merged card. | merging, building (next round), merged (re-review approved), triage |
| merging | Approved, and in the merge queue or its gate. | merged, triage |
| merged | On main. | ready (reopened), reviewing (re-review after a contract change) |
| triage | Waiting for you, with its reason. | ready (retry), waiting (reopen), parked |
| parked | Waiting for me, with the question under Open questions. | ready |
