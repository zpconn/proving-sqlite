# proving-sqlite: rules for every role

Your role's instructions are in the file your session's prompt names; only the orchestrator acts on the root GOAL.md.

This project proves, with CBMC, that functions in SQLite 3.53.4's varint and record decoding have no undefined behavior for any input bytes, plus two round-trip properties, on three platform configurations, without changing a byte of SQLite. These rules are GOAL.md §0, condensed. Every role obeys them. If this file and GOAL.md disagree, GOAL.md wins.

## Roles

- **Orchestrator** (Claude Code): writes cards, runs `tools/campaign.py`, handles triage, keeps the record. Never writes or fixes a proof.
- **Builder** (Codex, GPT-6 Astra): proves one card. Instructions: `agents/builder/GOAL.md`.
- **Reviewer** (Claude Code): judges one builder round, read-only. Instructions: `agents/reviewer/GOAL.md`.
- **Ledger agent** (Claude Code): tests LEDGER.md's assumptions. Instructions: `agents/ledger/GOAL.md`.
- **campaign.py**: a plain script, no model in its loop. It starts sessions, commits their work, merges what reviewers approve once the gate passes.

## 1. SQLite is the code under proof, unchanged

- `upstream/` holds the pinned `sqlite3.c`, `sqlite3.h` and source release byte for byte, hashed in `pin.txt`. Never edit it.
- `overlay/sqlite3.c` is upstream plus `PROOF(...)` spans and nothing else. `tools/check_overlay.py` deletes every PROOF span and requires the rest to equal upstream byte for byte.
- Harnesses call SQLite's own functions in the overlay.
- No agent copies, rewrites, simplifies or edits SQLite code, anywhere.

## 2. Frozen files

- At checkpoint 1, `proof.lock` records SHA-256 hashes of pin.txt, upstream/, GOAL.md, AGENTS.md, CLAUDE.md, agents/, PROPERTIES.md, TRUSTED.md, UB-CLASSES.md, proofs/spec/, proofs/CHECKS, proofs/CONFIGS, proofs/MUTANTS, tools/ and the gate's Makefile targets. The gate checks them.
- The one exception in tools/ is `tools/sessions.toml`. It may hold only command lines, model names and usage-limit patterns.
- Changing a frozen file needs Zach's approval: the patch and its evidence go under `evidence/approvals/`, unapplied until he answers.

## 3. Never weaken

No agent weakens a property, check, configuration, mutant, gate or ledger statement to make a proof pass. Propose the change instead, through the orchestrator.

## 4. Name the kind of claim

Use these four words, and use them exactly:
- **Proved**: CBMC verified it under the frozen checks (`proofs/CHECKS`).
- **Tested**: runtime evidence.
- **Assumed**: a LEDGER.md entry.
- **Trusted**: listed in TRUSTED.md (CBMC, its C semantics and library models, the preprocessor).

Every status line, report and result uses them. Nothing claims more than its evidence shows.

## 5. Roles stay separate

- Builders write proofs. Reviewers judge them. The orchestrator writes or fixes neither.
- Nobody reviews their own work.
- A reviewer runs in a fresh session, on the other vendor from the one that built the round it judges, and sees only the artifacts, never the builder's transcript. campaign.py refuses to start one otherwise.
- Sessions don't write git. campaign.py commits what a session leaves, checked against the paths its role may write.

## 6. The bytes are the adversary

- Data bytes are nondet: those of any record or page, and the string and blob contents a Mem points at.
- Requires may state sizes, allocation, aliasing and struct field values. They never constrain data bytes.
- If a read extent depends on the bytes, require the worst case (9 bytes for a varint).
- No `__CPROVER_assume` outside a harness's `/* SETUP */ ... /* END SETUP */` block: one per entry function, before the call under proof. No other way to end a path early (return or goto in an entry function, abort, exit, longjmp, `__VERIFIER_*`). No option that turns a check off. No unwinding without unwinding assertions. `tools/scan.py` enforces these.
- A real counterexample under requires that real callers guarantee is a finding, not an obstacle. Never add a requires to make one go away.

## 7. Nothing leaves the machine

Don't push, add a git remote, publish, post to the SQLite forum, email anyone or file bug reports. Findings stay in FINDINGS.md until Zach decides. Add no license file.

## 8. Budgets

- Every card has a token cap (GOAL.md Appendix B); the milestone's cap is 1B tokens. A token is anything a CLI reports: input, cache reads and writes, and output.
- campaign.py stops a session at its card's cap and records every session in `evidence/tokens.csv`.
- Builders check `.campaign/usage` in their worktree after each run. At 80% of the cap, report STUCK.

## 9. The machine

- Run CBMC and agent sessions under `nice -n 10`.
- At most 4 builder and reviewer sessions at once, together; fewer if CBMC makes the machine swap.
- Every CBMC run has a timeout, starting at 10 minutes per configuration.
- Long runs: builders wait for them in one blocking call, as agents/builder/GOAL.md §2.9 says, because Codex's sandbox kills background jobs. Claude sessions start them in the background with output in a file, or give the command a timeout longer than the run. Trust only output that ends with its `RESULT` line. A run a shell cut off is not a result.
- Keep scratch files under /tmp, never in tracked paths. A reviewer's /tmp is private to its session.

## 10. Models and subscriptions

- Builders: Codex with `gpt-6-astra`, xhigh effort on high-tier cards, high on standard.
- Reviewers: Claude Code, Opus 5.5 on high-tier cards, Sonnet 5.5 on standard.
- Ledger agent, orchestrator sessions and auditor: Claude Code, Opus 5.5.
- Every session runs on Zach's subscription through the vendor's own CLI (`claude -p`, `codex exec`). No API keys; campaign.py strips API-key variables from every session's environment. No flag that needs a key, such as claude's `--bare`.

## 11. Who commits to main

- `tools/campaign.py start` moves the orchestrator's checkout to branch `orch` and gives main its own checkout at `../proving-sqlite-wt/main`. `tools/campaign.py finish` reverses that.
- In between, only campaign.py commits to main. The orchestrator commits on orch and sends commits with `tools/campaign.py land`.
- Every commit campaign.py makes carries a `Campaign:` trailer saying what it is and what checked it.

## 12. Record

- `PROGRESS.md`: a status block of at most 40 lines, then a dated log.
- During the campaign, `tools/campaign.py status` and CAMPAIGN.md hold the card-by-card record.
- Bulky evidence goes in files under `evidence/`, each summarized in one line.
