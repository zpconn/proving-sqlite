# Approved: C-15's bounded P1 and its tools (2026-11-11)

- **The auditor**, relayed by Zach: "C-15's bounded package OK to land as patch.diff stands at wip/bounds 5111466. Verified: patch == branch diff; scan PASS; -k bounds 45/45, -k legacy 21/21, -k results 4/4, -k gate 4/4."
- **Zach:** keep K=4, N=256 in the gate. The diagnostic's K=8, N=256 PASS (1,036 s, default solver, 3600 s timeout) is recorded in proofs/C-15/NOTES.md as "measured once, not gated". C-15's round-5 builder writes it there, per its card. No timeout change.
- **Applied:** `patch.diff` on orch, byte for byte the diff of wip/bounds 5111466 against its merge base 72238ff. `git apply` was clean, and the applied files equal the branch's. LEDGER.md differs only by orch's own A-005 restatement, which the patch doesn't touch.
- **proof.lock:** rewritten after the commit, 59 files (`RESULT lock PASS 59 files`), tools/native.py included.
- **Follow-ups**, a small frozen change before C-17 merges, with the auditor's OK on its diff:
  1. T-015's check: a conditional target in the function's assigns (`c: x`) matches only a loop target in a group with the same condition. A match is refused if the function's body assigns any identifier the target names. Tests: both cases fail the build.
  2. Scan rule 16: BOUNDS names the tail terms allowed after `<buffer> + <offset>` (C-15: `mem_offset`), instead of any constant local. A BOUNDS comment says each buffer's size must equal the largest extent its bounds allow. Tests: a constant −1 shift fails the proof, and a +1 shift fails coverage.
  3. C-15's round-5 reviewer checks tests/bounded/C-15-1.c itself: exact-size heap buffers for the key, cases past both bounds, and the seven-member frame check. That goes in the card.
