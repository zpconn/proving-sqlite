# HANDOFF: setup session to campaign session (2026-11-10)

Read with GOAL.md, AGENTS.md and PROGRESS.md. The setup session did §0 to §2; the campaign session does §3 onward.

## State
- **Checkpoint 0:** reported 2026-11-08 at d26a1d4 (pilot). Zach approved corrections 1–8 and gave decisions B–E that day (evidence/bringup/13-checkpoint0.md). The auditor's follow-ups were approved on 2026-11-09, at 246ae0f.
- **Checkpoint 1:** reported 2026-11-09 at 71447f2. The fixes (D1, D2, D4, Q2, Q4, Q5, fixes 1–7) were made on 2026-11-10 at 8fbb0c8. Zach approved checkpoint 1 at 8fbb0c8 on 2026-11-10, with four decisions:
  1. builders run in bubblewrap;
  2. pending mutants aren't run, and the §5 gate fails on them;
  3. codex refuses to start if ~/.codex/AGENTS.md, AGENTS.override.md, hooks.json, agents/ or /etc/codex exists;
  4. record_format.h's comment-only D4 change is accepted without re-review.
- **proof.lock:** commit 4b851e7, covering 38 files (`tools/lock.py check`).
- **`tools/campaign.py status`:** campaign not started, daemon not running, scope C-01 and C-02 (the pilot's). C-01 is merged at r2, C-02 at r1, and the queues are empty. C-03 to C-20 aren't in campaign state yet; `start` adds them as waiting (see known issue 1). Last full gate: PASS, 880 s, 2026-11-08 14:17.

## What bring-up decided or found
- **Contracts** are separate `contract_<fn>` declarations in proofs/contracts/<fn>.h. SQLite's text gets only loop annotations, in PROOF spans in overlay/. A proof enforces one contract (02-contracts.md).
- **Tools:** CBMC 6.11.0 with goto-cc on gcc 13.3.0. The default solver is minisat2; a proof may pick cadical, glucose, `--z3` or `--smt2` (z3 4.8.12) with `<name>_SOLVER` (01-pins.md, prove.py).
- **Usage counting:**
  - codex: input (which includes cache reads) + cache writes + output, from the rollout log, less the thread's total when the job began.
  - claude: input + cache reads + cache writes + output, summed over message_delta events.
  - Caps are enforced in tokens (10-cli.md).
- **Usage-limit patterns** are in tools/sessions.toml, taken from the strings each CLI binary ships. No limit was hit in bring-up, so no real limit message has been observed.
- **Pilot** (12-pilot.md): 7 sessions, 6,615,364 tokens, 40.6 minutes.
  - C-02 merged in 1 round, C-01 in 2.
  - Astra builders used 11–18M tokens an hour, Sonnet reviewers 4–6M.
  - Gate runs: C-02 239 s, C-01 568 s, full 880 s.
  - A killed builder resumed on the same thread.
- **What GOAL.md got wrong:** PROGRESS.md "What bring-up showed GOAL.md or the plan got wrong", items 1–14. Plus §3.1's bare `tools/campaign.py start`: see known issue 1.

## Checks for the campaign session to run first
1. `make gate CARD=C-02`: must end `RESULT gate C-02 PASS`, lock check included. At the handoff it ended `RESULT gate C-02 PASS 402s 0 failed` (evidence/checkpoint1/12-handoff-gate-C-02.log).
2. `tools/campaign.py selftest`: must pass. At the handoff it passed 102/102 (12-handoff-selftest.txt).
3. `tools/campaign.py status`: must match **State** above.

If any of these fails, stop and tell Zach.

## Open questions and known issues
1. **Start with every card named.** campaign state still holds the pilot's scope, C-01 and C-02. `start` changes the scope only when given `--cards` (campaign.py:2186), and the daemon works only on scoped cards (1334). A bare `tools/campaign.py start` would therefore find its scope all merged and finish. Run:
   `tools/campaign.py start --cards C-01,C-02,C-03,C-04,C-05,C-06,C-07,C-08,C-09,C-10,C-11,C-12,C-13,C-14,C-15,C-16,C-17,C-18,C-19,C-20`
   Then check that status lists all 20 cards, C-03 to C-20 waiting or ready.
2. **Plain `make gate` (§5) fails until every card has merged.** It fails while any mutant is pending, which today means 49 mutants on 18 cards. Full gates during the campaign use `ALLOW_PENDING=1`, as campaign.py's land does. `make gate CARD=C-NN` counts only C-NN's own proofs.
3. **Codex builders can't background a command;** the sandbox kills it. They wait in the foreground, which the builder prompt and HOWTO say. At round 6 a card goes to triage (D4).
4. **Stale pilot records.** results.csv's lp64-be rows predate -funsigned-char and are regenerated at each card's next merge. The pilot's merges of main, 4a793a2 and 3d01a2e, have no Campaign: trailer.
5. **LEDGER.md entries are drafts** (A-001 to A-005) until the cards that use them settle. A-001 is exact: max(nKey, 1) + 8 bytes.
6. **Changing a frozen file needs Zach.** Put the patch and its evidence under evidence/approvals/, then land it with an updated proof.lock (§0.3, §3).

## Where everything is
- Plan and rules: GOAL.md, AGENTS.md, PROGRESS.md; role instructions in agents/builder/GOAL.md and agents/reviewer/GOAL.md.
- Statements: PROPERTIES.md (P1–P3, departures D1–D4), LEDGER.md, TRUSTED.md, UB-CLASSES.md.
- Cards: cards/C-01.md to C-20.md, with run order in five waves in evidence/checkpoint1/01-scope.md.
- Proofs: proofs/ (HOWTO.md, CHECKS, CONFIGS, MUTANTS, spec/, contracts/, include/, C-NN/). The annotated SQLite is overlay/, the pin is upstream/ and pin.txt.
- Tools: tools/ (campaign.py, prove.py, gate.py, mutate.py, scan.py, lock.py, check_overlay.py, cards.py, results.py, tests/). Session commands are in tools/sessions.toml, the one file in tools/ that isn't frozen.
- Campaign record: `tools/campaign.py status` and CAMPAIGN.md; reports/, reviews/, results.csv, RESULTS.md. The state and session logs are in ../proving-sqlite-wt/state/.
- Evidence:
  - evidence/bringup/ (§1, the pilot, checkpoint 0);
  - evidence/checkpoint1/ (README.md, the checkpoint 1 list and fixes);
  - evidence/spec/, evidence/gate/, evidence/results/;
  - session tokens in evidence/tokens.csv, orchestrator tokens in evidence/orchestrator/tokens.csv.
