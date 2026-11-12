# Approved: part 2, HOWTO's "Bounded proofs", TRUSTED.md's T-015 wording, a finding-review role (2026-11-11)

- **The auditor**, relayed by Zach: "Part 2 (wip/part2 6248d88): OK to land with one prompt change." The change is that the finding-review reviewer also rebuilds and runs F-002's repro and its clean control itself, in $TMPDIR in the foreground, and compares them with evidence/orchestrator/F-002/. If Codex's content filter stops the session (T-005), it is parked for Zach, with no fallback to Claude.
- **The change, made in 97f8a65** (README.md, "The auditor's OK"). patch.diff is wip/part2 1c0a4c9 against wip/t015-followup, and patch-6248d88.diff is the one approved.
- **Applied** on orch after part 1 landed (main 200d655, full gate PASS 4139 s) and the daemon restarted on main's campaign.py (21:38). `git apply` was clean, and the applied files equal the branch's. proofs/HOWTO.md is frozen from part 1, so this land carries this record and proof.lock.
- **proof.lock** was rewritten after the commit: 60 files.
- **Also in this land:** C-15's card points to proofs/HOWTO.md ("Bounded proofs") again, instead of the approval record's copy.
