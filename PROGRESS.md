# PROGRESS

## Status (2026-11-08 17:30, setup session, after checkpoint 0)

**Done:** instructions installed, machine checked (evidence/bringup/machine.txt), GOAL.md §0 and §1; checkpoint 0's decisions A–E and the auditor's fixes C1–C10 (below; evidence/bringup/13-checkpoint0.md). **Next:** the auditor rechecks the fixes; then §2.

| § | Item | Result | Evidence |
|---|---|---|---|
| 1.1 | Pins | 3.53.4 pinned; SOURCE_ID and release-log SHA3 match; src zip manifest = check-in; CBMC 6.11.0 (SAT minisat2/cadical/glucose, SMT z3) | 01-pins.md, pin.txt |
| 1.2 | Contracts on separate declarations | `f/c` enforces c on f, fails a false ensures, replaces calls; works for statics. **Choice: proofs/contracts/<fn>.h** | 02-contracts.md |
| 1.3 | Loop contracts | while: applied, bad invariant and measure caught. do-while: only `do PROOF(...){`, not after the condition | 03-loops.md |
| 1.4 | Checks | 11 options + float-to-int pass; all 13 toys fire; UB-CLASSES.md written | 04-checks.md, UB-CLASSES.md |
| 1.5 | Configurations | lp64-le, ilp32-le, lp64-be: probe and preprocessing confirm width, byte order, SQLite branch | 05-configs.md, 05-probe.txt |
| 1.6 | Builds | goto-cc whole overlay ≈5.7 s, 0.6 GB per config; one TU per harness | 06-builds.md |
| 1.7 | Coverage | `cbmc --cover location`; flags the toy's unreachable line | 07-coverage.md |
| 1.8.1 | Varint probe | 1M random + boundaries round-trip, 0 sanitizer reports; VarintLen 9 / 10 / 10 at 2^63−1 / 2^63 / 2^64−1: P2 stands | 08-probes.md |
| 1.8.2 | Over-read probe | ASan heap-buffer-overflow READ at 38190 via 92137: A-001 premise holds | 08-probes.md |
| 1.9 | Tools | check_overlay, scan, mutate, prove, lock, gate, make targets; 52/52 tests | 09-tools.md |
| 1.10 | Agent CLIs | both: headless on subscription, running token counts, kill+resume, 15-min command, sandbox | 10-cli.md, tools/sessions.toml |
| 1.11 | Coordinator | campaign.py; selftest 31/31 | 11-coordinator.md, 11-selftest.txt |
| 1.12 | Pilot | C-01 merged (2 rounds), C-02 merged (1); kill+resume; planted bug caught; full gate PASS | 12-pilot.md |

Evidence paths are under evidence/bringup/. Pilot: 7 sessions, 6.62M tokens, 41 session-minutes; C-01 225 and C-02 450 properties per configuration, CBMC ≤ 1 s each; coverage 100%; mutants 16/16.

**Checkpoint 0 decisions, done** (each with a tool test or selftest step; 13-checkpoint0.md has the detail):
- A: corrections 1–8 applied to GOAL.md (§1.3–§1.5, §1.9, §2.4, §3.1, Appendix A), builder §2.6/§2.9, AGENTS.md §9, HOWTO.
- B: lp64-be adds -funsigned-char; the probe checks char signedness; scan allows the flag.
- C1–C10: scan (path enders, SETUP discipline, card-dir files, symlinks, preds.h growth, COVER), gate (includes check, preds.h users), coverage (Unreached lines), lock (missing after freeze), campaign.py (vendors fixed, command guards, reviewer sandbox, trailers on merges, mode/symlink refusal, results provenance).
- D: Codex can block: two sessions.toml settings plus the builder's wait advice. 15-minute wait: 748,078 tokens before, 36,925 after.
- E: auth-failure patterns pause the vendor, add a triage item, resume with `campaign.py resume-vendor`.
- Tests: tool tests 95/95, selftest 49/49, full gate PASS (13-tool-tests.txt, 13-selftest.txt, 13-full-gate.log).
- Auditor follow-up 3 done: "## Unreached lines" entries are one line or a range within one uncovered stretch, with a reason, and fail if the run covers them; tool tests 104/104.
- Auditor follow-up 1 done: the gate calls tools/prove.py instead of make on card Makefiles and skips one load_card rejects; tool tests 97/97, `make gate CARD=C-02` PASS (13-checkpoint0.md).

**Open questions for Zach:**
1. SQLite 3.54.1 is out; the pin stays 3.53.4 per §1.1.
2. Codex builders had ChatGPT connectors (Gmail, Sites deploy, ~300 tools), web search and subagents available despite `--ignore-user-config`; the pilot never used them, and they are now disabled. Anything else to turn off?
3. Claude's login now expires 2026-12-07 22:27 UTC. An expired login now pauses the vendor with a triage item instead of failing cards.

## What bring-up showed GOAL.md or the plan got wrong

1. **Appendix A line numbers** are one past the line naming each function, for all of them. sqlite3CorruptError is at 191373, not 191392. The macros are at 22361–22369 and 91930–91934. Cards cite the naming line (01-lines.txt).
2. **do-while loop contracts** (§1.3, builder §2.6): clauses after the condition don't parse in CBMC 6.11. They go between `do` and the body, and the invariant must hold at the top of each iteration. scan.py enforces this, and proofs/HOWTO.md says it.
3. **Long runs under Codex** (builder §2.9, reviewer §1.5): Codex's sandbox kills a command's background children, even `setsid nohup`, when the command returns. Builders must run long commands in the foreground. The builder prompt and HOWTO say so; Claude reviewers can still background.
4. **Float-to-integer check** (§1.4): CBMC has no such option alone. `--conversion-check` also flags defined and implementation-defined casts, so CHECKS runs it as a restricted second pass.
5. **Configurations** (§1.5): goto-cc's `-m64` silently resets the architecture to x86_64 little-endian, so lp64-be must not pass it. ilp32-le needs gcc-multilib, which Appendix 6 doesn't list (Zach installed it today). Without `--slice-global-inits`, lp64-be runs out of CBMC object IDs.
6. **RESULT last** (§1.9): `make -C` prints "Leaving directory" after it unless `GNUMAKEFLAGS=--no-print-directory` is set; campaign.py sets it for every session and gate.
7. **Claude sessions** (§0.10, §1.10): they run in `--permission-mode auto` inside bubblewrap. This session's auto-mode classifier refused a test launch with bypassPermissions.
8. **Mutants:** each line carries `card=` (the card whose proofs must kill it), so a P1 card's gate never depends on a P2/P3 card that merges later. The full gate still runs every mutant against every proof.

## Notes for §2

- Ledger drafts so far: C-01's builder proposed one for sqlite3PutVarint's 9-byte output buffer (reports/C-01-b2.md), to be numbered in §2.3 with the three boundary contracts and A-001.
- Every commit campaign.py makes now carries a Campaign: trailer, its merges of main into card branches and orch included (C8). The pilot's two merges of main (4a793a2, 3d01a2e) predate this and have none.
- results.csv's lp64-be rows predate -funsigned-char; the next merge that reruns each card regenerates them. The full gate already passes with it.
- Token counting: codex counts input (which already includes cache reads) + cache writes + output; claude counts input + cache reads + cache writes + output.

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
