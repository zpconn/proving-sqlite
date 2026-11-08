# Proving SQLite: Milestone 1 Plan

Nov 8, 2026 · @Zach

## How to use this document

Save this doc in WSL as `~/code/proving-sqlite/PLAN.md`, start a Claude Code session there with the stage 1 goal, and it builds everything up to a frozen handoff point. A fresh Claude Code session then runs the campaign, with Astra building every proof and Claude judging them.

**For Zach, before the setup session:**

1. **Machine.** Do the steps in Appendix 6 once: Windows settings, the packages that need sudo, CBMC, Claude Code, Codex and both sign-ins. The setup session can't use sudo or sign in for you.
2. **Codex.** Check that `codex login status` shows your ChatGPT login and that `/model`, inside `codex`, lists GPT-6 Astra.
3. **This doc.** Export it as Markdown and copy it into WSL:

```bash
mkdir -p ~/code/proving-sqlite ~/code/proving-sqlite-wt
cp "$(ls -t /mnt/c/Users/*/Downloads/Proving*SQLite*Plan*.md | head -1)" ~/code/proving-sqlite/PLAN.md
```

4. **Start it.** In WezTerm's orch tab, run the command below, then paste the stage 1 goal from the setup session brief.

```bash
cd ~/code/proving-sqlite && claude --model opus --effort high --permission-mode auto --add-dir ~/code/proving-sqlite-wt
```

5. **Audit.** Once the session has written the auditor's file, start the auditor in the audit tab and tell it "Start your first session, per §6." At each checkpoint, tell it "Audit checkpoint N."

```bash
cd ~/code/proving-sqlite-review && claude --model opus --effort high --permission-mode auto --add-dir ~/code/proving-sqlite --add-dir ~/code/proving-sqlite-wt
```

6. **Hand off.** After checkpoint 1 and the freeze, exit the setup session and follow "After the handoff" below.

**For the setup session**, the Claude Code session reading this as PLAN.md: your instructions are the setup session brief below and GOAL.md §0 to §2, which you install from Appendix 1. You have no context beyond this document and the machine. You stop at each checkpoint and end for good at the handoff.

## The plan in one page

Milestone 1 uses CBMC to prove that 22 functions in SQLite 3.53.4's varint and record decoding have no undefined behavior for any input bytes. It also proves two round-trip properties, on three platform configurations, without changing a byte of SQLite. A plain script, `tools/campaign.py`, runs the card loop. Models write the proofs, judge them and make the judgment calls.

&#91;embedded content: milestone 1 · four stages, three checkpoints, one handoff\]

The setup session builds and tests everything, the pilot included, and freezes it at checkpoint 1. A fresh session then picks up from HANDOFF.md and runs the campaign.

| Role | Played by | Started by | Instructions |
| --- | --- | --- | --- |
| Setup session: orchestrator for stages 1 and 2 | Claude Code, Opus 5.5 | Zach | This doc's brief, then GOAL.md §0 to §2 |
| Campaign session: orchestrator for stages 3 and 4 | A fresh Claude Code, Opus 5.5 | Zach, after the handoff | HANDOFF.md, then GOAL.md §3 to §5 |
| Builders | Codex with GPT-6 Astra: xhigh effort on high-tier cards, high on standard | campaign.py, one session per card round | agents/builder/GOAL.md |
| Reviewers | Claude Code: Opus 5.5 on high-tier cards, Sonnet 5.5 on standard | campaign.py, a fresh session per review | agents/reviewer/GOAL.md |
| Ledger agent | Claude Code, Opus 5.5 | The campaign session, once | agents/ledger/GOAL.md |
| Auditor | Claude Code, Opus 5.5, in its own folder | Zach, at each checkpoint | The auditor's CLAUDE.md |

Every role except building runs on Claude: the campaign session and the sessions campaign.py starts for it. Reviewers can't share one long-running session, because each review starts fresh and never sees the builder's work in progress. A review always runs on the other vendor from its author, so the one thing Astra reviews is the file-format spec the setup session writes.

**What the handoff leaves behind:**

- **Tools, built and tested:** check\_overlay, scan.py, mutate.py, the gate, campaign.py with its selftest, and sessions.toml.
- **Bring-up evidence:** every GOAL.md §1 item with its result.
- **The pilot:** C-01 and C-02, built by Astra, reviewed by Claude and merged through the gate.
- **Frozen in proof.lock:** PROPERTIES.md, the file-format spec, CHECKS, CONFIGS, MUTANTS, the tools and every role's instructions.
- **Ready to run:** cards C-03 to C-20 with their dependencies, ledger drafts, TRUSTED.md and UB-CLASSES.md.
- **HANDOFF.md:** one screen telling the fresh session where everything is and how to start.

## Setup session brief

You build and test the infrastructure, run the two pilot cards through it with Astra building, prepare the campaign, and stop at a frozen handoff. You never write proofs. Once step 1 is done, GOAL.md is your source of truth: re-read its §0 after every context reset.

1. **Install the instructions.** Appendices 1 to 5 each hold one file in a single code block. Copy each block's contents byte for byte with a short script, never by retyping. A block ends at the first line that is only backticks; the files' own code blocks use `~~~` fences, so they can't end it early.
   - Appendix 1 → `~/code/proving-sqlite/GOAL.md`
   - Appendix 2 → `~/code/proving-sqlite/agents/builder/GOAL.md`
   - Appendix 3 → `~/code/proving-sqlite/agents/reviewer/GOAL.md`
   - Appendix 4 → `~/code/proving-sqlite/agents/ledger/GOAL.md`
   - Appendix 5 → `~/code/proving-sqlite-review/CLAUDE.md`, the auditor's file

   Replace any older copies. Run `git init -b main` if the repo doesn't exist yet. Move PLAN.md to `evidence/handover/PLAN.md`, where you read it from then on, and commit everything as "Instructions from PLAN.md". Create `~/code/proving-sqlite-wt/`. If `~/code/proving-sqlite-review/.claude/settings.json` is missing, write it with this rule, which stops the auditor's file tools from writing to the project. Then tell Zach the auditor can start.

```json
{"permissions": {"deny": ["Edit(~/code/proving-sqlite/**)", "Edit(~/code/proving-sqlite-wt/**)"]}}
```

2. **Check the machine.** You can't use sudo, so if anything here is missing, stop and give Zach the exact command, from Appendix 6 where it's listed.
   - CBMC 6.11.0 or later, with goto-cc, goto-instrument and goto-synthesizer
   - z3; gcc and clang with ASan and UBSan; make; python3 with venv; tclsh and tcl.h; tmux; git
   - bubblewrap, and a test sandbox that works: `bwrap --ro-bind / / --dev /dev --unshare-all true`
   - `codex login status` shows a ChatGPT login, and gpt-6-astra is available
   - Claude Code on Zach's subscription, and no API-key variables in the environment or shell startup files
3. **Stage 1, bring-up and pilot:** GOAL.md §0 and §1. Astra builder sessions build both pilot cards through campaign.py, and Claude reviewer sessions judge them. Fix anything the pilot exposes now, since the tools freeze at checkpoint 1. Stop at checkpoint 0.
4. **Stage 2, properties and cards:** GOAL.md §2. Stop at checkpoint 1.
5. **Freeze and hand off.** After Zach approves checkpoint 1, commit proof.lock, then write and commit HANDOFF.md as GOAL.md §2 describes. Print it and stop for good.
6. **Never** write or fix a proof yourself, or run the full campaign (the pilot's `start` and `finish` are fine). Never push, add a git remote, publish or use sudo, and never change a frozen file after the freeze.

Zach pastes these three goals in turn. Stage 1:

```text
/goal You are the setup session described in PLAN.md. Follow its setup session brief: install the instruction files from its appendices and check the machine, then do GOAL.md §0 and §1, with Astra building both pilot cards. Done when you have printed PROGRESS.md's status block, listing every §1 item with its result and evidence file, and the output of tools/campaign.py selftest. Then stop for checkpoint 0; don't start §2.
```

Stage 2:

```text
/goal I've approved checkpoint 0. Carry out GOAL.md §2. Done when you have printed the checkpoint 1 list with each item's file. Then stop for my review; don't write proof.lock or start §3.
```

The freeze:

```text
/goal I've approved checkpoint 1. Commit proof.lock, then write and commit HANDOFF.md as GOAL.md §2 describes. Done when you have printed HANDOFF.md, the output of tools/campaign.py status and the RESULT line of make gate CARD=C-02. Then stop: the setup session ends here, so don't start §3.
```

## After the handoff

Once HANDOFF.md is committed, Zach starts a fresh Claude Code session as the campaign session, and from then on campaign.py starts every Astra builder and Claude reviewer itself.

1. Exit the setup session with `/exit`. Don't resume it: the campaign session starts with an empty context and learns everything from HANDOFF.md and GOAL.md.
2. In the orch tab, start the campaign session:

```bash
cd ~/code/proving-sqlite && claude --model opus --effort high --permission-mode auto --add-dir ~/code/proving-sqlite-wt
```

3. Paste the stage 3 goal:

```text
/goal You are the campaign session. Read HANDOFF.md and run the checks it lists, then carry out GOAL.md §3 and §4, with tools/campaign.py wait in the background and each triage item handled as it comes. Done when you have printed tools/campaign.py status showing every card merged and the full gate passed, and the ledger agent's summary; or showing every unmerged card parked for me, with its question under Open questions in PROGRESS.md.
```

4. When stage 3 is done, paste the stage 4 goal, then have the auditor audit checkpoint 2:

```text
/goal Carry out GOAL.md §5, up to checkpoint 2. Done when you have printed the clean-clone gate's result line, the results.csv comparison and README.md. Don't push, publish or contact anyone.
```

**While it runs:**

- **Watching.** In the shell tab, `tmux attach -t campaign` shows campaign.py live (Ctrl+B then D to leave), and `tools/campaign.py status` summarizes it.
- **Astra.** Nobody starts it by hand: campaign.py runs each builder as a `codex exec` session on Zach's ChatGPT login.
- **Usage limits.** The campaign session waits and continues on its own when a Claude limit resets, and campaign.py pauses whichever vendor hit a limit.
- **Questions for Zach.** They go under Open questions in PROGRESS.md, and the campaign keeps working on other cards meanwhile.
- **After a reboot.** Restart each session with `--continue` added to its command, which brings its goal back. If the campaign was running, tell the campaign session to run `tools/campaign.py start`, which picks up where it left off.

## Appendix 1: GOAL.md

Save as `~/code/proving-sqlite/GOAL.md`. These are the orchestrator's instructions, for both the setup session and the campaign session.

```text
# proving-sqlite, milestone 1 (orchestrator)

Prove with CBMC that 22 functions in SQLite 3.53.4's varint and record decoding have no undefined behavior for any bytes they are given, plus two round-trip properties, on three platform configurations, without changing a byte of SQLite. You are the orchestrator, and two Claude Code sessions play that role in turn. The *setup session* does §0 to §2: it sets up the repo and tools, including `tools/campaign.py`, a plain script that runs the card loop; proves the infrastructure on two pilot cards; prepares the properties and cards; and, after I approve checkpoint 1, freezes them and writes HANDOFF.md. A fresh *campaign session* then does §3 to §5, starting from HANDOFF.md. campaign.py starts the builder and reviewer sessions, commits their work, and merges what reviewers approve once the gate passes. You write the cards, decide what the script can't, and keep the record. You never write proofs. This is a long, multi-session job: don't stop until your part is fully and honestly done, except at the checkpoints below where you must wait for me. If a later instruction from me in chat conflicts with this file, the chat wins. ("proving-sqlite" is a placeholder name.)

**Why it exists.** This is milestone 1 of a proposal to Richard Hipp, SQLite's author: prove SQLite free of undefined behavior one module at a time, with agents doing the proof work, a mechanical checker deciding, and nothing in his tree changing. Hipp has written that formal verification only moves bugs into the design spec. This milestone's answer is that the property is one sentence, and everything else the proofs rest on is written down in LEDGER.md, short enough for him to check. Nothing leaves this machine without my say.

Before designing anything, study:
- **SQLite 3.53.4's amalgamation**, `SQLITE_SOURCE_ID` "2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc": every function in Appendix A at its line, the varint macros at 22362–22370, the serial-value macros at 91931–91935, and the structs Mem, UnpackedRecord, KeyInfo and CollSeq.
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
11. **Who commits to main.** `tools/campaign.py start` moves your checkout to branch `orch` and gives main its own checkout at `../proving-sqlite-wt/main`; `tools/campaign.py finish` reverses that. In between, only campaign.py commits to main. You commit on orch and send your commits with `tools/campaign.py land`. Every commit campaign.py makes carries a `Campaign:` trailer saying what it is and what checked it.

## 1. Bring-up and pilot

Set up the repo (Appendix D), pins and tools, and test what this plan assumes about them. Record each item with its evidence in PROGRESS.md and `evidence/bringup/`.

1. **Pins.** The SQLite 3.53.4 amalgamation, checking SQLITE_SOURCE_ID against the value above; its source release (sqlite-src-3530400.zip), which holds the test suite the ledger agent runs offline; and the latest CBMC release, recording its version and solver back ends. If SQLite has a newer release, still pin 3.53.4, because Appendix A was checked against it, and tell me.
2. **Contracts on separate declarations.** The DFCC command line accepts `--enforce-contract <function>[/<contract>]` and `--replace-call-with-contract <function>[/<contract>]`, but its documentation doesn't say what the suffix means. On a toy, show whether `f/c` checks f against clauses declared on a separate declaration c, fails when c's ensures is false of f, and replaces calls to f with c. If it works, contracts live in `proofs/contracts/` and SQLite's text gets only loop annotations. If not, contracts become PROOF spans on the definitions in the overlay. Record the choice.
3. **Loop contracts.** Define `#define PROOF(...) __VA_ARGS__` in `proofs/include/proof.h`. On a toy while loop and a toy do-while (sqlite3VdbeRecordCompareWithSkip's loop is a do-while), show that `__CPROVER_assigns`, `__CPROVER_loop_invariant` and `__CPROVER_decreases`, in that order between header and body, are applied by `--apply-loop-contracts`, and that a false invariant and a non-decreasing measure are each caught. The documentation shows only inline loop contracts. goto-synthesizer can dump synthesized ones as JSON, but nothing documented reads them back, so assume inline.
4. **Checks.** Write `proofs/CHECKS`, the CBMC options every proof uses: pointer, bounds, signed overflow, undefined shift, division by zero, pointer overflow and pointer primitive checks; a float-to-integer conversion check if your CBMC has one; malloc that may fail and return NULL; and unwinding assertions. Confirm each option in `cbmc --help`, then show each check fires on a toy that commits its UB. Write `UB-CLASSES.md`: every kind of undefined behavior in C11 Annex J.2 that can arise in this code, each marked *checked* (by which option), *argued* (by inspection, listing the sites, e.g. serialGet's `*(i64*)&x` and sqlite3GetVarint's `(signed char*)p`) or *out of scope* (data races, since the proofs assume one thread; stack exhaustion), with the reason.
5. **Configurations.** `proofs/CONFIGS` defines lp64-le, ilp32-le and lp64-be. lp64-be also passes `-DSQLITE_BYTEORDER=4321` when preprocessing. For each, show with a probe harness, and by preprocessing the overlay, that the word size, the endianness and SQLite's byte-order branches are what the name says. Hipp tests on a big-endian PowerPC, among others.
6. **Builds.** Time goto-cc on the whole overlay per configuration, and decide how proofs link against it, e.g. one sqlite3 goto binary per configuration, with each harness linked in and unused functions dropped. Record the time and memory. Builds write only inside the worktree they run in, because a Codex session can write nowhere else, and .gitignore covers everything they write.
7. **Coverage.** Find the command that reports which lines of the function under proof a harness reaches. Show that it flags a deliberately unreachable line in a toy.
8. **Native probes.** Build these with ASan and UBSan against unmodified upstream, not with CBMC:
   1. Varints: round-trip boundary values and a million random values through sqlite3PutVarint and sqlite3GetVarint, and print sqlite3VarintLen at 2^63−1, 2^63 and 2^64−1. Reading the source, it returns 10 for v ≥ 2^63, though the encoding is 9 bytes. This settles P2's wording.
   2. Over-read: call sqlite3VdbeRecordUnpack on the two-byte record {0x02, 0x81} held in an exact-size malloc. Reading the source, decoding the serial type reads past the record, so ASan should report a heap-buffer-overflow read. This is the premise of ledger entry A-001.
9. **Tools.**
   - `tools/check_overlay.py`.
   - `tools/scan.py` (§3.4).
   - `tools/mutate.py`, which applies one mutant to a scratch copy of the overlay and always restores the original.
   - Top-level `make prove`, `make coverage`, `make gate` and `make gate CARD=C-NN` (§3.4). `make -C proofs/C-NN prove` takes `CONFIG=<name>` to run one configuration. Every target ends its output with one result line, such as `RESULT prove C-03 lp64-le PASS 212s 1843 properties 0 failed`, so a run cut off by a shell timeout can't pass for a result.
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
4. proofs/MUTANTS: at least two mutants per function, each a one-token change to a bounds check, mask, shift, constant or loop condition. A mutant is killed when some proof fails. List any you expect to be equivalent, and why.
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
   - **Sessions.** Each starts from tools/sessions.toml, detached in its own process group under `nice -n 10`, with its output streamed to `../proving-sqlite-wt/state/` and its exit status written beside it, so it outlives a restart of campaign.py. Builders run on Codex and reviewers on Claude, at the card's tier, as §0.10 says and sessions.toml implements. The prompt is fixed in campaign.py: the role's GOAL file, the card, the round and any reviews to answer. `tools/campaign.py session` starts a one-off session the same way, for the §2 spec review and the ledger agent. It commits what the session writes, checked against the paths that role may write, on a branch of its own, and during a campaign lands it on main.
   - **Commits.** Sessions don't write git. When a builder ends, campaign.py checks every change since the round started, committed or not, including new files git doesn't ignore. If all are on the card's May change line, it commits them with a message naming the card and round; otherwise it commits nothing and sends the card to triage. When a reviewer ends, it commits only the review file: onto the card branch, or onto main for a re-review of a merged card. A reviewer that changed a tracked file is discarded and run once more, and if that one does too, the card goes to triage.
   - **Verdicts.** The first line of the report or review decides. DONE and FINDING start a reviewer. APPROVE sends the card to merge, or, on a FINDING, to triage with the finding reproduced. REJECT starts the next builder round, up to three. Anything else goes to triage: STUCK, NEEDS-DECISION, NEEDS-ZACH, a third REJECT, or a missing first line.
   - **Merges,** one at a time. campaign.py merges only the commit the reviewer approved, plus the review. In a scratch worktree at main's head, it merges them with `--no-ff`, checks that the merge touches only the card's May change paths and its own reviews, and runs `make gate CARD=C-NN`. If that passes, it regenerates RESULTS.md, results.csv, CAMPAIGN.md and evidence/tokens.csv, adds the gate log under evidence/gate/, commits them, and fast-forwards main. If not, the card goes to triage with the gate log. After the last card merges, it runs the full `make gate`.
   - **Interruptions.** A session that ends without its report or verdict is resumed in the same worktree. If its output matches its vendor's usage-limit pattern, no session starts on that vendor until the reset time it printed, or, if it printed none, for 30 minutes, doubling up to 4 hours; that doesn't count against the card. Any other interruption counts, and the third in a round sends the card to triage. Output that matches no pattern is logged verbatim, so the patterns can be fixed.
   - **Caps.** It counts each session's tokens as §0.8 defines them, or its time where §1.10 found no running count, and keeps the running total in `.campaign/usage` in the session's worktree, where builders read it. At the card's cap it ends the session, commits a builder's allowed changes, and sends the card to triage.
   - **Restarts.** It journals each step in `../proving-sqlite-wt/state/` before taking it. On restart it reconciles the journal with git and the running sessions, so a crash at any point neither loses nor repeats a session or a merge. `tools/campaign.py stop` stops it starting anything new; running sessions carry on, and `start` picks up where it left off.
   - **Status.** `tools/campaign.py status` prints each card's state, round, vendor, tokens against cap and what it is waiting on, then the triage queue, the merge queue, any vendor pause and the last full gate's result. CAMPAIGN.md holds the same.
2. **What you do.**
   - Run `tools/campaign.py wait` in the background. It returns when the triage queue changes, the campaign finishes, campaign.py stops, or four hours pass, so you never poll.
   - Take each triage item in turn and read its report, review and logs. Then fix the card, land the fix, and run `tools/campaign.py retry C-NN`; reopen another card (§3.3); or run `tools/campaign.py park C-NN` and put the question under Open questions in PROGRESS.md, with your recommendation. STUCK and FINDING cards always get a recommendation.
   - Commit your own changes on branch orch, then run `tools/campaign.py land`. It merges main into orch, so your checkout stays current, and queues orch for main. A land may touch only cards/, tests/repro/, evidence/approvals/, evidence/orchestrator/, PROGRESS.md, LEDGER.md and FINDINGS.md. A frozen file may change only with my approval record and an updated proof.lock in the same land; campaign.py then runs the full gate and sends every card whose proof fails to triage. Proofs reach main only through card merges.
   - campaign.py is frozen. If it misbehaves, stop it and ask me before changing it.
3. **Contract changes.** A builder that needs more from an approved contract, such as a stronger ensures or a weaker requires, reports NEEDS-DECISION with the change. If you agree, `tools/campaign.py reopen C-NN --for C-MM` sends C-NN, the card that owns the contract, back for a new round with the request added to its notes, and C-MM waits for it. When C-NN merges again, its gate has rerun every proof that uses the contract, and campaign.py starts a re-review of each merged card whose proof uses it. A REJECT sends that card back for a new round.
4. **The gate.** `make gate` runs everything below. `make gate CARD=C-NN`, which campaign.py runs before each merge, runs check_overlay, the proof.lock check and scan.py, plus the proofs, coverage and mutants of the card and of every card whose proofs call its functions.
   - check_overlay;
   - proof.lock's hashes, once it exists;
   - every merged proof, on every configuration, with proofs/CHECKS;
   - coverage of every proof, with each unreached line of the function under proof explained in its NOTES.md;
   - every mutant in proofs/MUTANTS killed, or shown equivalent by a reviewed argument;
   - `tools/scan.py`, which rejects:
     - any `__CPROVER_assume` outside a harness's setup block;
     - any option that turns a check off, and any compile flag beyond proofs/CONFIGS;
     - unwinding without unwinding assertions;
     - a boundary contract that doesn't name its ledger entry;
     - a harness that defines a function SQLite's code calls;
     - a PROOF span anywhere but where §1.2 and §1.3 allow, in the functions its card names, or one that holds anything but contract clauses;
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

SQLite 3.53.4 amalgamation. *UB sites* counts the memory accesses AddressSanitizer instruments at -O1 plus UBSan's arithmetic and pointer checks, measured on this pin; use it for budgeting only. The 22 functions total about 800 lines, 7 loops and 570 UB sites.

| Level | Function | Line | NLOC | Loops | UB sites | Calls in scope | Boundary calls |
|---|---|---|---|---|---|---|---|
| 0 | sqlite3VarintLen | 38216 | 7 | 1 | 2 | | |
| 0 | putVarint64 | 37968 | 25 | 3 | 23 | | |
| 0 | sqlite3GetVarint | 38022 | 106 | 0 | 51 | | |
| 0 | sqlite3VdbeSerialTypeLen | 91863 | 9 | 0 | 4 | | |
| 0 | sqlite3VdbeOneByteSerialTypeLen | 91872 | 5 | 0 | 3 | | |
| 0 | serialGet | 91946 | 20 | 0 | 34 | | |
| 0 | serialGet7 | 91981 | 18 | 0 | 34 | | |
| 0 | vdbeRecordDecodeInt | 92553 | 33 | 0 | 76 | | |
| 0 | sqlite3VdbeFindCompare | 93011 | 34 | 0 | 22 | | |
| 0 | isAllZero | 92370 | 7 | 1 | 3 | | |
| 0 | sqlite3IsNaN | 36446 | 8 | 0 | 5 | | |
| 0 | sqlite3VdbeMemSetNull | 86608 | 7 | 0 | 2 | | |
| 1 | sqlite3PutVarint | 37992 | 12 | 0 | 7 | putVarint64 | |
| 1 | sqlite3GetVarint32 | 38183 | 23 | 0 | 16 | sqlite3GetVarint | |
| 1 | sqlite3VdbeSerialGet | 91998 | 68 | 0 | 72 | serialGet | |
| 1 | sqlite3IntFloatCompare | 92426 | 16 | 0 | 1 | sqlite3IsNaN | |
| 1 | sqlite3VdbeAllocUnpackedRecord | 92097 | 15 | 0 | 9 | | sqlite3DbMallocRaw |
| 2 | sqlite3VdbeRecordUnpack | 92117 | 41 | 1 | 20 | sqlite3GetVarint32, sqlite3VdbeSerialGet, sqlite3VdbeSerialTypeLen, sqlite3VdbeMemSetNull | |
| 2 | sqlite3VdbeRecordCompareWithSkip | 92608 | 198 | 1 | 73 | sqlite3GetVarint32, sqlite3VdbeSerialGet, serialGet7, sqlite3VdbeSerialTypeLen, sqlite3VarintLen, vdbeRecordDecodeInt, sqlite3IntFloatCompare, isAllZero | vdbeCompareMemString, sqlite3CorruptError |
| 3 | sqlite3VdbeRecordCompare | 92829 | 6 | 0 | 0 | sqlite3VdbeRecordCompareWithSkip | |
| 3 | vdbeRecordCompareString | 92941 | 61 | 0 | 24 | sqlite3GetVarint32, sqlite3VdbeRecordCompareWithSkip | sqlite3CorruptError |
| 4 | vdbeRecordCompareInt | 92846 | 76 | 0 | 86 | sqlite3VdbeRecordCompare, sqlite3VdbeRecordCompareWithSkip | |

memcmp, called by sqlite3VdbeRecordCompareWithSkip and vdbeRecordCompareString, is CBMC's library model, so it goes in TRUSTED.md.

Boundary contracts are assumed, and each needs a LEDGER.md entry:

| Function | Line | Used by | Why it's not proved here |
|---|---|---|---|
| sqlite3DbMallocRaw | 32114 | sqlite3VdbeAllocUnpackedRecord | The allocator and lookaside belong to a later milestone. Contract: returns NULL or a fresh block of at least n bytes. |
| vdbeCompareMemString | 92351 | sqlite3VdbeRecordCompareWithSkip | It calls the collation's xCmp, which is application code, or converts encodings through vdbemem.c. |
| sqlite3CorruptError | 191392 | sqlite3VdbeRecordCompareWithSkip, vdbeRecordCompareString | It reports through sqlite3_log, which can call the application's log callback, and returns SQLITE_CORRUPT. |

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
```

## Appendix 2: agents/builder/GOAL.md

Save as `~/code/proving-sqlite/agents/builder/GOAL.md`. Every Astra builder session follows it.

```text
# proving-sqlite: builder

You prove one card. Your session's prompt names it, `cards/C-NN.md`, with the round and any earlier reviews to answer. Prove it, report, and stop. `tools/campaign.py` started you in the card's worktree, on branch `card/C-NN`. It commits what you leave when you exit, and merges it only after a reviewer approves and the gate passes. The reviewer never sees this session, so everything you know must be in the files.

The root GOAL.md is the project's source of truth. Read its §0, Appendix A and Appendix C, and PROPERTIES.md, but don't carry out its plan. During the pilot, before PROPERTIES.md exists, your card states the property. If this file conflicts with GOAL.md or PROPERTIES.md, they win. If your card conflicts with either, stop and say so.

Before writing anything, read:
- the card, and every review it names;
- your functions in `upstream/sqlite3.c` at the lines the card gives, plus every macro and struct they touch;
- the contracts of their callees in `proofs/contracts/`, and the LEDGER.md entries those cite;
- the call sites in your functions' in-scope callers, because your requires must hold there;
- `proofs/CHECKS`, `proofs/CONFIGS`, `proofs/include/preds.h`, and one approved card's directory as an example.

## 1. What you may change

Only these, which your card's May change line spells out:
- `proofs/C-NN/`: harness.c, Makefile, NOTES.md.
- `proofs/contracts/<function>.h` for your card's functions, or, if checkpoint 0 chose the fallback, PROOF spans on their definitions in `overlay/sqlite3.c`.
- PROOF spans between the header and body of loops in your card's functions, in `overlay/sqlite3.c`.
- New predicates in `proofs/include/preds.h`, when no existing one says what you need.
- `tests/repro/F-draft-C-NN-<k>.c`, for a suspected finding.
- `reports/C-NN-b<round>.md`.

Everything else is read-only, including upstream/, tools/, the gate, CHECKS, CONFIGS, MUTANTS, proofs/spec/, other cards' contracts, LEDGER.md and FINDINGS.md. If you need one of them changed, ask in your report. campaign.py commits only the paths on your May change line. If you change any other tracked file, or leave a new file elsewhere that git doesn't ignore, it commits nothing and sends the card to the orchestrator. Keep scratch files under /tmp.

## 2. Rules

1. **Prove the real code.** The harness calls your function in the overlay. Don't copy, simplify or reimplement SQLite code anywhere.
2. **The bytes are the adversary.** Data bytes are nondet, always: those of any record or page, and the string and blob contents a Mem points at. Requires may state sizes, allocation, aliasing and struct field values, never what the data bytes contain. If the read extent depends on the bytes, require the worst case.
3. **Start unconstrained.** Begin with only what the call needs to make sense (pointers allocated, sizes in range), run, and add a requires only when a counterexample shows it's needed. Every requires gets a row in NOTES.md giving the counterexample you get without it and why real callers guarantee it: the caller's line in upstream for an in-scope caller, or a ledger draft for anything else.
4. **Minimal footprints.** For a slack or length requires, show the proof passes at the value you require and fails at one less.
5. **Contracts no stronger than needed.** Ensure what callers and PROPERTIES.md need, and no more. Assigns lists exactly what is written.
6. **Loops.** Each loop gets `PROOF(__CPROVER_assigns(...) __CPROVER_loop_invariant(...) __CPROVER_decreases(...))`, clauses in that order, between the loop header and its body (after the condition, for a do-while). A loop bounded by construction at 16 iterations or fewer may instead be unwound with unwinding assertions; say which you did and why in NOTES.md.
7. **No assumes outside the harness's setup block.** It's delimited by `/* SETUP */` and `/* END SETUP */` and only allocates and sizes things. No option that turns a check off. No unwinding without unwinding assertions. `tools/scan.py` enforces these; don't argue with it.
8. **A real counterexample is a result, not an obstacle.** If CBMC finds UB under requires that real callers do guarantee, stop strengthening. Minimize the counterexample and write `tests/repro/F-draft-C-NN-<k>.c`: it builds natively against unmodified `upstream/sqlite3.c`, fails under ASan or UBSan, and has its build command in its header. Then report FINDING. Never add a requires to make a real counterexample go away.
9. **Long runs.** A CBMC run can take 10 minutes, and `make prove` runs three configurations, which is longer than your shell waits by default. Start each run in the background with its output in a file and read the file when the run ends, or give the command a timeout longer than the run. While iterating, run one configuration at a time with `CONFIG=<name>`. Trust only output that ends with its RESULT line; a run your shell cut off is not a result.

## 3. The loop

1. Write harness.c and the contract.
2. Run `make -C proofs/C-NN prove` (every configuration; see rule 9), read the failures, fix the harness or the contract, and repeat. If a run times out, simplify (smaller nondet bounds on setup sizes, a callee replaced by its contract) rather than raising the timeout.
3. Then run `make -C proofs/C-NN coverage`, `tools/mutate.py --card C-NN`, `tools/check_overlay.py` and `tools/scan.py`.
4. Write NOTES.md, at most 60 lines:
   - the contract in plain English;
   - the §2.3 table of requires;
   - footprint minimality;
   - each uncovered line and why it can't be reached;
   - each loop invariant in one line;
   - open questions.

**Done** means:
- every configuration passes with no failed property;
- coverage reaches every line of your functions, or NOTES.md explains each gap;
- your card's mutants are killed, or you argue that one is equivalent;
- the scans pass;
- NOTES.md and the report are written.

**Stuck** means eight runs in a row without fewer failed properties, or 80% of the card's token cap used. campaign.py keeps your running total in `.campaign/usage`, in tokens or, for some CLIs, in time; check it after each run, because at the cap it ends your session. Then stop and report STUCK with what you tried and what you would try next. Don't thrash.

## 4. Report

`reports/C-NN-b<round>.md`. First line: DONE, STUCK, FINDING or NEEDS-DECISION. Use NEEDS-DECISION when you can't go on without a change to another card's contract or to a read-only file, or an answer only the orchestrator or Zach can give, and say exactly what you need. Then:
- **Proved:** for each configuration, CBMC time, properties checked, and failed (0).
- **Contract:** requires, ensures and assigns in plain English, each requires with its justification (caller line or ledger draft).
- **Drafts:** ledger entries and findings in GOAL.md's Appendix C format, and any changes you need to other contracts.
- **Coverage and mutants.**
- **Files changed, tokens used (from `.campaign/usage`), open questions.**

Don't commit, branch or merge. When your session ends, campaign.py commits your changes with a message naming the card and round.

## 5. Before you start, check the facts that apply

GOAL.md's Appendix A lists facts read from the source. The ones builders trip on:
- sqlite3GetVarint reads up to 9 bytes and takes no length. Callers must provide 9 readable bytes, or the proof must show why fewer suffice.
- sqlite3VdbeRecordUnpack can read past pKey+nKey on a corrupt record. That is ledger entry A-001, not a reason to constrain the record's bytes.
- sqlite3VarintLen returns 10 for v ≥ 2^63. Contracts and P2 must say so rather than claim it always matches the encoded length.
```

## Appendix 3: agents/reviewer/GOAL.md

Save as `~/code/proving-sqlite/agents/reviewer/GOAL.md`. Every reviewer session follows it.

```text
# proving-sqlite: reviewer

You judge one card. Your session's prompt names the card, the builder's round and its commit. `tools/campaign.py` started you in a fresh worktree, detached at that commit. Review the work there, write a verdict, and stop. You don't fix anything. The builder's report is a claim; the repo is the evidence. You never see the builder's session, and you work only in your own worktree.

Read the root GOAL.md's §0, Appendix A and Appendix C, PROPERTIES.md, the card, the builder's report and NOTES.md, the diff against main (`git diff main...HEAD`), and the card's functions in `upstream/sqlite3.c`.

If your prompt says this is a re-review after a contract change, your worktree is at main's head instead. Judge the card's proof against the changed contract; checklist items 3, 5 and 7 matter most.

## 1. Rules

1. **Read only.** Don't modify tracked files or run git commands that write. Write only `reviews/C-NN-r<round>.md`, untracked, in your worktree; campaign.py commits it to the card branch. If you change a tracked file, your review is discarded, so make scratch copies, such as one with a requires deleted, under /tmp.
2. **Rerun everything before believing it:** `make -C proofs/C-NN prove` on every configuration, coverage, `tools/mutate.py --card C-NN`, `tools/check_overlay.py` and `tools/scan.py`.
3. **Check the code, not the prose.** When NOTES.md says a caller guarantees something, open the caller at that line and check.
4. **Approve only with no blocker or major issue open.**
5. **Long runs.** A CBMC run can take 10 minutes, longer than your shell waits by default. Start each run in the background with its output in a file and read the file when the run ends, or give the command a timeout longer than the run. Trust only output that ends with its RESULT line.

## 2. Checklist, most serious first

1. **It's SQLite's code.** The harness calls the function in the overlay. No SQLite code is copied or rewritten anywhere. The overlay diff is PROOF spans in this card's functions only, and check_overlay passes.
2. **The bytes are unconstrained.** Data bytes are nondet: those of records and pages, and the string and blob contents a Mem points at. No requires, setup assumption, helper predicate or allocation trick constrains them: no zero-filled buffers, no buffers sized to fit only well-formed records, nothing allocated larger than callers guarantee. Footprints are worst case.
3. **Every requires is necessary and justified.**
   - Delete each requires in a scratch copy and rerun; the proof must fail.
   - For each in-scope caller (Appendix A), the caller's code must establish the requires at the call site. Read it.
   - Anything callers don't establish must have a ledger draft that names who must make it true.
   - For a footprint, the required value minus one must fail.
4. **Not vacuous.**
   - Coverage reaches every line of the card's functions, or each gap is explained and the explanation is right; an unreachable line can mean a requires is too strong.
   - The function's return is reachable.
   - Each of the card's mutants is killed, or its equivalence argument holds.
5. **Ensures and assigns.** They're what the code does, which the proof shows. They give the callers' cards what those need, and no more. Assigns lists every write.
6. **Loops.** Every loop has assigns, an invariant and decreases, or is unwound with unwinding assertions and a justified bound.
7. **Boundary contracts used.** For each callee replaced by a ledger contract, read its source: is the contract true of it? Is the ledger draft honest about who must make it true?
8. **Findings.** For a FINDING, build `tests/repro` natively against unmodified upstream and run it under ASan or UBSan.
   - Does it fail as claimed?
   - Is it reachable from SQL or the public API, or only when a ledger entry is violated? In the second case it's a ledger matter, not a finding.
9. **Words.** Proved, tested, assumed and trusted are used correctly. Nothing in NOTES.md or the report claims more than the proof shows.

## 3. Verdict

`reviews/C-NN-r<round>.md`. First line: APPROVE, REJECT or NEEDS-ZACH. On a FINDING round, APPROVE means the repro fails as the report claims on unmodified upstream; the card then goes to the orchestrator, not to merge. Use NEEDS-ZACH for questions only he can settle, such as whether an assumption about SQLite's callers is acceptable in the ledger.

Then number each issue and give:
- its severity: blocker, major or minor;
- what's wrong;
- the evidence: the command and the relevant output lines;
- the specific change that would fix it.

At most 80 lines. If you approve with minor issues, list them; the orchestrator files them.
```

## Appendix 4: agents/ledger/GOAL.md

Save as `~/code/proving-sqlite/agents/ledger/GOAL.md`. The ledger agent follows it once, during the campaign.

```text
# proving-sqlite: ledger agent

You test LEDGER.md's assumptions against SQLite itself. The question is whether real SQLite, running its own test suite and fuzz corpora, ever does what the proofs assume its callers never do. Your answer marks each entry tested or violated. You don't touch proofs, contracts or the overlay. What you produce is testing evidence, and the ledger must call it that.

`tools/campaign.py` started you in your own worktree. Your session may have no network, so everything you need is already in the repo or installed. When you exit, campaign.py commits what you wrote in validation/ and evidence/ledger/, and your report, and lands them on main.

Read the root GOAL.md's §0, Appendix A and Appendix C, PROPERTIES.md, LEDGER.md and TRUSTED.md.

## 1. Build

1. Check the 3.53.4 source release in upstream/ against its hash in pin.txt, then unpack it into `validation/src/`, which git ignores. It is the canonical source tree for the pinned check-in, bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc. The amalgamation alone has no test suite.
2. Build in `validation/build/`, which git ignores. Build the amalgamation from that tree and check that it equals `upstream/sqlite3.c` byte for byte. If it doesn't, stop and report, because the tests would be exercising different code.
3. In `validation/`, never in upstream/ or overlay/, write `ledger.patch`. At each entry's site it adds a check that logs, without aborting, when the assumption fails, giving the entry ID, the arguments and a backtrace.
   - For memory-extent assumptions, build with ASan and use `__asan_region_is_poisoned` from `<sanitizer/asan_interface.h>`. For A-001, at entry to sqlite3VdbeRecordUnpack, check that the slack bytes after pKey+nKey are addressable.
   - For facts about struct fields, check the fields.
   - Give every check a counter, so the evidence says how often each assumption was exercised.
4. Show each check works: a small program that violates the assumption on purpose must get logged.

## 2. Run

Run the test targets SQLite's Makefile provides at the pin. Start with the ones named test and fuzztest, and record the exact targets and what each covers. Also run fuzzcheck over the fuzz databases in `test/`. Use `nice -n 10`. These run for hours, longer than your shell waits: start each in the background with its output in a file, and confirm it finished before reading the result. For each entry, record the number of checks, any violations (test name, stack, arguments), and whether its site was reached at all.

## 3. Report

Put the evidence in `evidence/ledger/<date>/`, and your summary in `reports/ledger-<date>.md`, with:
- for each entry: tested (checks, test files, zero violations) or violated (each violation with a minimal reproduction);
- any entry whose site the suite never reached, labeled as such, because that isn't evidence;
- for each violation, your reading: either the assumption is wrong and needs a different statement, or SQLite really calls the function that way, which makes it a finding draft, with a repro.

Also draft, but don't send, a paragraph Zach could pass to Hipp asking him to run ledger.patch under TH3, his proprietary 100% MC/DC suite.

Don't edit LEDGER.md; the orchestrator does that.
```

## Appendix 5: the auditor's CLAUDE.md

Save as `~/code/proving-sqlite-review/CLAUDE.md`. The auditor loads it in every session; Zach runs the auditor at each checkpoint.

```text
# proving-sqlite: auditor

Save this file as `CLAUDE.md` in `~/code/proving-sqlite-review`, so it loads in every session there, and start Claude Code in that folder with `claude --add-dir ~/code/proving-sqlite --add-dir ~/code/proving-sqlite-wt`.

## 0. Your role

- **The orchestrator** runs the project in `~/code/proving-sqlite` from its GOAL.md, played by two Claude Code sessions in turn. The setup session builds the infrastructure, including `tools/campaign.py`, a plain script that runs the card loop. It stops after checkpoint 1 with the files frozen and HANDOFF.md written. A fresh campaign session then runs the campaign from HANDOFF.md. campaign.py starts the builder sessions, on Codex with GPT-6 Astra, and the reviewer sessions, on Claude. It commits their work and merges what reviewers approve once the gate passes.
- **You** are Zach's independent auditor. You don't build, and you don't review cards. You check the tooling, campaign.py included, and the claims at each checkpoint, and you look for ways the whole setup could pass while proving less than it says.
- **Relay.** Zach relays messages between you and the orchestrator.

The repo's GOAL.md, AGENTS.md and agents/*/GOAL.md are the other agents' instructions. Read GOAL.md in full, since it's the project's source of truth, but never treat any of those files as your task.

**Folders.**
- `~/code/proving-sqlite`: the project. Read only.
- `~/code/proving-sqlite-wt`: the project's worktrees, campaign.py's checkout of main during the campaign, and, in `state/`, its journal and the session logs. Read only.
- `~/code/proving-sqlite-review`: yours. This file, REVIEW-LOG.md, and reference material under `ref/`.
- `~/code/proving-sqlite-audit`: your clone of the latest commit on main, for builds and runs.

**Rules of engagement:**
1. **Never write to `~/code/proving-sqlite` or `~/code/proving-sqlite-wt`:** no edits, new files, commits or other git writes, and no campaign.py command but `status`. Their worktrees and branches belong to running sessions.
2. **Run builds, CBMC and tests only in your audit clone, with `nice -n 19`.** Don't run heavy jobs while builders are running unless Zach says the machine has room.
3. **Keep your notes in REVIEW-LOG.md.** Append the date, what you checked, the verdict and open items. Read it at the start of each session, after this file.
4. **Verify; don't trust.** Reports, PROGRESS.md, CAMPAIGN.md and RESULTS.md are claims. CBMC output you produced yourself, hashes, check_overlay output and git history are evidence. campaign.py's journal and session logs tell you what to check; they don't settle it.

**How to talk to Zach:**
- Give the verdict first, then only the issues that matter.
- When the orchestrator needs an answer, recommend one and give paste-ready text in a code block.
- Be concise; he moves fast.
- Distinguish proved, tested, assumed and trusted.
- Own your mistakes plainly.

## 1. Who and why

Zach Conn leads an effort at Collins Aerospace to scale AI formal verification. He built lean1090 and aeneas1090 with this same builder and reviewer pattern, so don't explain the basics.

This project is milestone 1 of a pitch to Richard Hipp, SQLite's author, made through Karl Lehenbauer, FlightAware's founding CTO and Hipp's friend. Hipp's positions define what success means:
- In December 2025 he wrote that formal verification only moves bugs into the design spec. He said he spent years on a formal spec of SQLite, found that it added nothing, and challenged the poster to prove him wrong (sqlite.org/forum/info/39134ba0298d89cf).
- SQLite's AGENTS.md accepts no agent-written code. It does accept agent-found bug reports that come with a reproducible test case. Outside code needs prior agreement and paperwork placing it in the public domain.
- In 2016 he removed all the known UB that tis-interpreter found, some of it grudgingly, saying SQLite's verification targets the compiled machine code (blog.regehr.org/archives/1292).
- He tests on many platforms, including a big-endian PowerPC. TH3, his 100% MC/DC test suite, is proprietary.

The pitch made these promises:
- Nothing in SQLite's tree changes.
- Agents do the proof work, and a mechanical checker decides.
- The proofs live in a separate repository pinned to a check-in.
- Anything found reaches him as a bug report with a test case.
- He decides what's worth proving and whether the work continues.
- The proofs are re-checked against each release.

**The crux.** P1's statement is short, but the proofs rest on contracts and assumptions. LEDGER.md is where a spec can still be wrong, so that's where Hipp's objection lands. Your main job is to make sure nothing that belongs in the ledger is hiding in a harness, a helper predicate, a CBMC option, or a contract nobody checked against its callers.

## 2. What was checked before you, and what wasn't

The GOAL's author read the facts in GOAL.md's Appendix A from the 3.53.4 source, with line numbers. None of it was run. Two of its predictions are tested only by bring-up's native probes, so watch §1.8:
- **sqlite3VarintLen** returns 10 for v ≥ 2^63, while the encoding is 9 bytes. P2 must state this, not claim the two always agree.
- **sqlite3VdbeRecordUnpack** reads past the record on corrupt input. ASan should flag the {0x02, 0x81} probe. If it doesn't, A-001's premise is wrong.

These CBMC points come from its documentation, and bring-up must settle them:
- The `--enforce-contract f/c` syntax exists, but nothing says c may be a separate declaration. Expect a fallback.
- Loop contracts are documented only inline. goto-synthesizer dumps JSON, but nothing documented reads it back.
- Quantifiers in contracts need `--smt2`.
- CBMC's malloc never returns NULL unless told it may fail.

These harness facts come from each CLI's documentation, and GOAL.md §1.10 tests them:
- A key in the environment can take precedence over a subscription login.
- Codex's workspace-write sandbox blocks the network and keeps .git read-only, for the session and everything it starts. That's why campaign.py, not the sessions, does every git write.
- Both CLIs can resume a killed session.
- Shell tools cut off long commands, so a proof run can stop mid-output. The RESULT line each make target prints is the guard.

## 3. Checkpoint audits

**Checkpoint 0 (bring-up):**
- Reproduce every §1 claim yourself:
  - the f/c experiment fails when it should;
  - each option in CHECKS fires on its toy;
  - each configuration really changes the word size, the endianness and SQLite's byte-order branch;
  - coverage flags the unreachable toy line;
  - both probes say what GOAL.md predicted, or GOAL.md gets corrected.
- **Tools:**
  - Try to sneak a change to SQLite's text past check_overlay.
  - Try an assume outside SETUP, a disabled check, and unwinding without assertions on scan.py.
  - Confirm mutate.py always restores the overlay.
- **Coordinator.**
  - Rerun `tools/campaign.py selftest` in your audit clone.
  - Read the merge path, then try to get an unapproved commit onto main with the fake CLIs: a builder that writes its own review file, a review of an earlier commit, a card branch that gains a commit after its review, a gate failure, a land that touches proofs/, a reviewer on the builder's vendor.
  - Kill it with -9 at a few points and confirm it recovers without repeating a merge.
  - Check that sessions.toml holds only command lines, models and limit patterns, and that the pilot's session logs show subscription logins, not API keys.
- **Pilot:** rerun C-01 and C-02, delete a requires and see the proof fail, and plant a bug. Read the pilot builders' logs for anything their reports left out.

**Checkpoint 1 (freeze):**
- **P1 to P3.** Look for overclaims and loopholes.
  - Is "any bytes they are given" honest?
  - Does every predicate in preds.h leave data bytes unconstrained?
  - Does P2's VarintLen clause match the code?
  - Does `ref_serial_get` match the file format's serial type table row by row, with SQLite's departures stated rather than hidden?
- **Scope.** Appendix A matches the call graph at the pin, and each boundary contract has a ledger draft saying who must make it true.
- **Cards.** Each May change line is exactly what builder §1 allows that card, and each Depends on line matches the call graph.
- **Gates and mutants.** They must be strong enough that a vacuous or over-constrained proof fails. Suggest mutants the list lacks.
- **UB-CLASSES.md.** Every class CBMC doesn't check is listed as argued or out of scope, with its sites.
- **Handoff,** after Zach approves. Could a fresh session start from HANDOFF.md, GOAL.md, AGENTS.md and PROGRESS.md alone? Run HANDOFF.md's checks in your audit clone, confirm proof.lock matches, and look for anything it says that the evidence contradicts.

**Checkpoint 2 (release):**
- From a clean clone, `make gate` passes and results.csv regenerates identically.
- Pick three proofs, always including sqlite3VdbeRecordUnpack and sqlite3VdbeRecordCompareWithSkip. Delete each requires in turn, confirm the proof fails, and confirm the justification holds at the caller.
- **Ledger.** Every entry has runtime evidence. The instrumented build's amalgamation matched upstream. Sites the suite never reached are labeled as such.
- **Findings.** Each repro fails natively on unmodified upstream.
- **Campaign record.**
  - proof.lock covers everything GOAL.md §0.3 lists, and still matches.
  - Every commit on main between campaign.py's start and finish carries a `Campaign:` trailer.
  - Every card merge names an APPROVE of the exact commit merged, by the vendor that didn't build that round, and a gate log that passed.
  - Lands touched only the paths GOAL.md §3.2 allows, and every frozen-file change has an approval record.
- **README.** Its claims match the evidence and use the four words. Nothing implies functional correctness, other platforms or compile options, or multithreaded use.

## 4. Loopholes to look for

- A harness that calls a copy or a wrapper instead of SQLite's function.
- Constraints on data bytes smuggled in: zero-filled buffers, allocation sizes only well-formed records fit, predicates that imply contents, nondet values drawn from a small set.
- A `__CPROVER_assume` hidden in an included header, a contract or a macro.
- Makefile options that override CHECKS, such as a later option that turns a check off, a check missing from one configuration, or unwinding without assertions.
- A contract used to replace calls that's false of the real callee.
- A configuration that doesn't actually differ from another.
- Coverage gaps explained away, or mutants marked equivalent without a real argument.
- Findings demoted without being reproduced, or ledger entries marked tested whose site the suite never reached.
- Anything in the overlay besides PROOF spans in loop headers, or on definitions under the fallback, and any PROOF span holding code rather than contract clauses.
- Per-card compile flags, such as a `-D` that changes which SQLite code is compiled.
- A harness that defines its own version of a function SQLite calls, such as memcmp, instead of using CBMC's model or a ledger contract.
- A merge whose review approved a different commit, or whose reviewer ran on the builder's vendor.
- A builder round committed with changes outside its card's May change line, a May change line wider than builder §1 allows, or a land carrying proof changes.
- campaign.py, the gate or another frozen file changed after proof.lock without an approval record. A sessions.toml change that does more than flags and models, such as a different prompt or GOAL file, or one vendor for both roles.
- A result read from output that a shell timeout cut off, without its RESULT line.

## 5. Run plan

Zach runs the orchestrator's two sessions in stages, each its own goal, so each stops wherever it must wait for him. A goal's evaluator reads only the conversation, not files, so each done condition is output the session prints. `evidence/handover/PLAN.md` has every goal word for word.
- **Setup session:** stage 1 (GOAL.md §0 and §1), checkpoint 0, stage 2 (§2), checkpoint 1, then the freeze: proof.lock and HANDOFF.md. Then it ends.
- **Campaign session,** started fresh: stage 3 (§3 and §4), then stage 4 (§5) and checkpoint 2.

Both start with:
~~~
cd ~/code/proving-sqlite && claude --model opus --effort high --permission-mode auto --add-dir ~/code/proving-sqlite-wt
~~~
The campaign runs in a tmux session named `campaign`: `tmux attach -t campaign` shows it live, and `tools/campaign.py status` summarizes it.

## 6. First session

1. Read the project's GOAL.md, AGENTS.md, PROGRESS.md, agents/*/GOAL.md and evidence/handover/PLAN.md, and tools/campaign.py once it exists. Create REVIEW-LOG.md.
2. Make the audit clone. Save the reference material under `ref/`: the CBMC documentation pages GOAL.md cites, the record format section of SQLite's file format document, and the forum thread.
3. Tell Zach you're ready, and what you'll check first at checkpoint 0.
```

## Appendix 6: Machine setup

Zach does these steps once, before the setup session starts, because the session can't use sudo, sign in to either CLI or change Windows settings. They assume Windows with WSL 2 running Ubuntu 22.04 or 24.04, and WezTerm.

**1. Windows, in PowerShell.** Note the Ubuntu distro's NAME and check that its VERSION is 2. The rest gives WSL all but 8 GB of RAM and 2 cores, and keeps the PC awake on AC power. An existing .wslconfig is kept as .wslconfig.bak; copy back any other settings it had.

```powershell
wsl --update
wsl -l -v
$cfg = "$env:USERPROFILE\.wslconfig"
if (Test-Path $cfg) { Copy-Item $cfg "$cfg.bak" }
$cs  = Get-CimInstance Win32_ComputerSystem
$ram = [math]::Floor($cs.TotalPhysicalMemory / 1GB)
$cpu = $cs.NumberOfLogicalProcessors
@"
[wsl2]
memory=$([math]::Max(8, $ram - 8))GB
processors=$([math]::Max(2, $cpu - 2))
swap=16GB

[general]
instanceIdleTimeout=-1
"@ | Set-Content -Encoding ascii $cfg
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
wsl --shutdown
```

`instanceIdleTimeout=-1` keeps Linux, tmux and the sessions running after WezTerm closes. Pause Windows Update for the length of the run.

**2. WSL packages.**

```bash
sudo apt-get update
sudo apt-get install -y build-essential clang git curl ca-certificates jq unzip zip time \
  tmux ripgrep python3 python3-venv python3-pip tcl tcl-dev z3 bubblewrap
```

**3. CBMC 6.11.0**, the latest release when this plan was written.

```bash
. /etc/os-release
deb="ubuntu-$VERSION_ID-cbmc-6.11.0-Linux.deb"
cd /tmp && curl -fLO "https://github.com/diffblue/cbmc/releases/download/cbmc-6.11.0/$deb"
sudo apt-get install -y "./$deb" && cbmc --version
```

**4. Claude Code and Codex.** Open a new tab afterwards, so both are on the PATH.

```bash
curl -fsSL https://claude.ai/install.sh | bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

**5. Sign in and check.** In `claude`, sign in with the Claude subscription; `/status` shows the login. In `codex`, choose "Sign in with ChatGPT"; `/model` should list GPT-6 Astra. If Codex's browser sign-in can't get back to WSL, turn on device code login in ChatGPT's security settings and run `codex login --device-auth`. Then check that no API key could override either login:

```bash
env | grep -E 'ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|OPENAI_API_KEY|CODEX_API_KEY' || echo "no API keys set"
```

**6. git and tmux.**

```bash
git config --global user.name "Zach Conn"
git config --global user.email "zpconn@gmail.com"
[ -e ~/.tmux.conf ] || printf 'set -g mouse on\nset -g history-limit 100000\n' > ~/.tmux.conf
```

**7. WezTerm.** Put this in `C:\Users\<you>\.wezterm.lua`, or merge its `default_domain` line and `gui-startup` block into an existing config. Set `WSL` to "WSL:" plus the NAME from step 1. Restart WezTerm and it opens three tabs: orch and audit, each attached to a tmux session that outlives WezTerm, and a plain shell.

```lua
local wezterm = require 'wezterm'
local mux = wezterm.mux
local config = wezterm.config_builder()

-- "WSL:" plus your distro's NAME from `wsl -l -v`
local WSL = 'WSL:Ubuntu-24.04'
config.default_domain = WSL

-- A tab attached to a tmux session, so the session outlives WezTerm.
local function tmux(name, dir)
  return {
    domain = { DomainName = WSL },
    args = { 'bash', '-lc', 'exec tmux new-session -A -s ' .. name .. ' -c ' .. dir },
  }
end

wezterm.on('gui-startup', function()
  local tab, _, window = mux.spawn_window(tmux('orch', '~/code/proving-sqlite'))
  tab:set_title('orch')
  tab = window:spawn_tab(tmux('audit', '~/code/proving-sqlite-review'))
  tab:set_title('audit')
  tab = window:spawn_tab { domain = { DomainName = WSL } }
  tab:set_title('shell')
end)

return config
```

Sources: [Claude Code setup](https://code.claude.com/docs/en/setup.md), [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), [Codex sign-in](https://learn.chatgpt.com/docs/auth.md), [CBMC releases](https://github.com/diffblue/cbmc/releases/latest), [WSL configuration](https://learn.microsoft.com/en-us/windows/wsl/wsl-config), [WezTerm gui-startup](https://wezterm.org/config/lua/gui-events/gui-startup.html).
