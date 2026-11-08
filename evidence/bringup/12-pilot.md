# §1.12 Pilot (2026-11-08 13:22–14:18)

`tools/campaign.py start --cards C-01,C-02` at 13:22:56, then `tools/campaign.py finish` at 14:18:22. Builders were Astra (codex, gpt-6-astra, effort high: both cards are standard tier). Reviewers were Claude (claude-sonnet-5-5). Every session's tokens are in `evidence/tokens.csv`; the card-by-card record is `CAMPAIGN.md`; gate logs are `evidence/gate/C-02-r1.log`, `C-01-r2.log` and `full-*.log`.

| Session | Card | Role, round | Model | Tokens | Minutes | Outcome |
|---|---|---|---|---:|---:|---|
| J0002 | C-02 | builder r1 | gpt-6-astra high | 334,100 | 1.8 | killed by me with SIGKILL mid-session (runner exit −9) |
| J0003 | C-02 | builder r1, resumed | gpt-6-astra high | 761,490 | 4.0 | DONE (`codex exec resume` on the same thread) |
| J0004 | C-02 | reviewer r1 | claude-sonnet-5-5 | 490,284 | 4.6 | APPROVE |
| J0001 | C-01 | builder r1 | gpt-6-astra high | 2,410,820 | 8.3 | DONE |
| J0005 | C-01 | reviewer r1 | claude-sonnet-5-5 | 820,636 | 8.7 | REJECT (major: the fixed 9-byte local buffer made both requires unnecessary) |
| J0007 | C-01 | builder r2 | gpt-6-astra high | 1,313,598 | 5.5 | DONE (SETUP-sized allocation; each requires shown necessary) |
| J0008 | C-01 | reviewer r2 | claude-sonnet-5-5 | 484,436 | 7.7 | APPROVE |
| | | | **total** | **6,615,364** | 40.6 | |

Rates: Astra builders spent 11–18M tokens per hour, Sonnet reviewers 4–6M. Caps are enforced in tokens, since both CLIs give running counts (10-cli.md), so these rates are only for budgeting.

**Proofs** (evidence/results/C-0N.json, results.csv):
- **C-01** (P1, 2 rounds). Proofs put64 (enforce contract_putVarint64, loops unwound at 10 with assertions) and put (enforce contract_sqlite3PutVarint, putVarint64 replaced by its contract). Per configuration (lp64-le, ilp32-le, lp64-be): 110 + 115 properties, 0 failed, CBMC under 1 s each, 15 s with build per proof. Coverage 18/18 lines of putVarint64 and 9/9 of sqlite3PutVarint on every configuration. Mutants M-001, M-002, M-003, M-006 and M-007: 5/5 killed. Requires: `__CPROVER_w_ok(p, 9)`; 8 bytes fails at the write to p[8] (37971). Ledger draft: callers outside milestone 1 must provide 9 writable bytes.
- **C-02** (P2, 1 round). One proof, the round trip, with the real code of all five functions and the getVarint32 macro. Per configuration: 450 properties, 0 failed, CBMC 0–1 s, 9–10 s with build. Coverage 133/133 lines (putVarint64 18, sqlite3PutVarint 9, sqlite3GetVarint 87, sqlite3GetVarint32 15, sqlite3VarintLen 4). Mutants M-004, M-005 and M-008 to M-016: 11/11 killed. The decoders get exactly n bytes; n−1 fails.
- **Gates:** C-02 merge 239 s PASS; C-01 merge 568 s PASS (C-01's and C-02's proofs, C-01's mutants); full `make gate` after the last merge 880 s PASS with 16/16 mutants killed.

**Kill and resume:** C-02's builder was killed at 13:24:46, 110 s in, with lp64-le already proved. The runner recorded exit −9; campaign.py counted interruption 1 and started J0003 at 13:24:56 with `codex exec resume 01a1bc9d-2244-72f3-…`. That session continued from its own context ("Proved on all three configurations…") and reported DONE.

**Planted bug** (`12-planted-bug.txt`; `tools/mutate.py --adhoc` on a scratch copy of the overlay, whose hash was unchanged afterwards):
- In putVarint64's copy loop, `j=n-1` → `j=n` (37986). C-02's P2 proof fails (round-trip length and value, and the suffix-unchanged check); C-01's P1 proofs pass it. That is correct, not a gap: the bug writes n+1 ≤ 9 bytes inside the proved footprint and reads the indeterminate `buf[n]`, so it is a wrong value, not UB. CBMC does not flag indeterminate reads; UB-CLASSES.md argues that class.
- `j>=0` → `j>=-1` (37986) fails C-01's put64 proof: buf lower bound, assigns and signed overflow.

**Found by the pilot and fixed on main after `finish`:** gate.py ran a card's proofs twice when a caller shared its functions (`cards.callers_of` returned the card itself). campaign.py's results collection dropped a card's mutant results when a later caller's gate regenerated its evidence; C-02's were restored from its own merge commit and RESULTS.md and results.csv regenerated with tools/results.py. The status columns were also reformatted. After the fixes: tool tests 52/52, selftest 31/31, and `make gate CARD=C-02` on main PASS in 365 s (`12-gate-C-02-after-fixes.log`).
**My error, found by the C-01 builder:** card C-01 said "both loops"; putVarint64 has three. The builder unwound all three.
